#!/usr/bin/python3
import os
import sys
import time
import shutil
import requests
from plexapi.server import PlexServer
from plexapi.library import LibrarySection
import ffmpeg
import json

movies=[]
tv=[]
config={}
vf_string="scale=%d:%d"

def readConfig(path="config.json"):
    global CONFIG
    global movies
    global tv
    global vf_string
    
    with open(path, 'r') as infile:
        CONFIG = json.load(infile)
    plex_url=CONFIG["Plex_IP"]+":"+str(CONFIG["Plex_Port"])
    if 'SSL' in CONFIG and CONFIG['SSL']:
        plex_url="https://"+plex_url
    else:
        plex_url="http://"+plex_url
    plex=PlexServer(plex_url, CONFIG["Plex_Token"])
    movies=plex.library.section(CONFIG["Movie_Library_Name"])
    tv=plex.library.section(CONFIG["TV_Library_Name"])
    if 'VF_Mod' in CONFIG["Optimize"] and len(CONFIG["Optimize"]["VF_Mod"]) != 0:
            vf_string=CONFIG["Optimize"]["VF_Mod"]+","+"scale=%d:%d"
        
def dprint(*names):
    if CONFIG["DEBUG"]:
        print(*names)
def get_video_codec(input_file):
    try:
        video_info = ffmpeg.probe(input_file)
        video_stream = next((stream for stream in video_info['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream is None:
            dprint('No video stream found')
            return None
        else:
            dprint(f"Video codec: {video_stream['codec_name']}")
            return video_stream['codec_name']
    except Exception as e:
        print(f'Error: {e}')
def probeVideoForResolution(input_file):
    try:
        probe = ffmpeg.probe(input_file)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream is None:
            print('No video stream found')
            return
        if 'h264' in video_stream['codec_name'] and CONFIG["ENABLE_HW_DECODE"]:
            hwdecode={"hwaccel":'cuvid', 'c:v':'h264_cuvid'}
        elif 'hevc' in  video_stream['codec_name'] and CONFIG["ENABLE_HW_DECODE"]:
            hwdecode={"hwaccel":'cuvid', 'c:v':'hevc_cuvid'}
        else:
            hwdecode={}
        width = int(video_stream['width'])
        height = int(video_stream['height'])
        
        # Downscale video to 1080p if above this resolution
        aspect_ratio = width / height
        height = CONFIG["Max_Resolution"]
        width = int(aspect_ratio * height)
        
        return {"width":width,"height":height,"aspect":"aspect_ratio","hwdecode":hwdecode}
    except Exception as err:
        print(f"Unexpected {err=}, {type(err)=}")
        return {"width":None,"height":None,"aspect":None,"hwdecode":{}}
    
def convert_video(input_file, output_file):
    try:
        probe=probeVideoForResolution(input_file)
        OPTIMIZE_ITERATIONS=len(CONFIG["Optimize"])
        if 'VF_Mod' in CONFIG["Optimize"]:
            OPTIMIZE_ITERATIONS=OPTIMIZE_ITERATIONS-1
        i=0
        while i < OPTIMIZE_ITERATIONS:
            if 'action' in CONFIG["Optimize"]["Optimize_"+str(i)]:
                if safeCopy(input_file, output_file):
                    break
            else:
                if probe["height"] is not None and probe["height"] > CONFIG["Max_Resolution"]:
                    stream = ffmpeg.input(input_file,**probe["hwdecode"]).output(output_file, vf=vf_string % (width, height), **CONFIG["Optimize"]["Optimize_"+str(i)])
                else:
                    stream = ffmpeg.input(input_file,**probe["hwdecode"]).output(output_file, **CONFIG["Optimize"]["Optimize_"+str(i)])
                if safeRunStream(stream, output_file):
                    break
            i=i+1
        
    except Exception as err:
        print(f"Unexpected {err=}, {type(err)=}") 
def cat_videos(video_files, output_file):
    if len(video_files) < 1:
        return False
    elif len(video_files) == 1:
        return convert_video(video_files[0], output_file)
    try:
        input_streams = [ffmpeg.input(file) for file in video_files]
        probe = probeVideoForResolution(video_files[0])
        
        i=0
        OPTIMIZE_ITERATIONS=len(CONFIG["Optimize"])
        if 'VF_Mod' in CONFIG["Optimize"]:
            OPTIMIZE_ITERATIONS=OPTIMIZE_ITERATIONS-1
        while i < OPTIMIZE_ITERATIONS:
            if 'action' in CONFIG["Optimize"]["Optimize_"+str(i)]:
                if safeCopy(input_streams, output_file):
                    break
            else:
                if probe["height"] is not None and probe["height"] > CONFIG["Max_Resolution"]:
                    stream=ffmpeg.concat(*input_streams, v=1, a=1,**probe["hwdecode"]).output(output_file, vf=vf_string % (width, height), **CONFIG["Optimize"]["Optimize_"+str(i)])
                else:
                    stream = ffmpeg.concat(*input_streams, v=1, a=1, **probe["hwdecode"]).output(output_file, **CONFIG["Optimize"]["Optimize_"+str(i)])
                if safeRunStream(stream, output_file):
                    break
            i=i+1

        
    except Exception as e:
        print('Error: ', e)
def safeCopy(input_file, output_file):
    try:
        if not isinstance(input_file, str):
            i=0
            while i < len(input_file):
                partnum=(i+1)
                dprint("Copying Part ",partnum)
                safeCopy(input_file[i], output_file.replace("."+CONFIG["Output_Format"],"_part"+str(partnum)+"."+CONFIG["Output_Format"]))
                i=i+1
            return True
        elif os.path.isfile(output_file) and os.path.isfile(output_file+".inprogress"):
            dprint("Detected incomplete copy: ",output_file+".inprogress")
            dprint("Removing files and retrying")
            delete(output_file)
            delete(output_file+".inprogress")
        elif os.path.isfile(output_file):
            dprint("Output File Exists: ", output_file)
            dprint("Skipping")
            return True
            
        mkdir(output_file)
        touch(output_file+".inprogress")
        dprint("Strarting copy for: ",output_file,".inprogress")
        copy(input_file,output_file)
        delete(output_file+".inprogress")
        dprint("Completed transcode for: ",output_file)
        return True
    except Exception as e:
        print('Error: ', e)
        return False
def safeRunStream(stream, output_file, input_file=None):
    if stream is None and input_file is not None:
        return safeCopy(input_file, output_file)
    elif stream is None and input_file is None:
        return false
    try:
        if os.path.isfile(output_file) and os.path.isfile(output_file+".inprogress"):
            dprint("Detected incomplete transcode: ",output_file,".inprogress")
            dprint("Removing files and retrying")
            delete(output_file)
            delete(output_file+".inprogress")
        elif os.path.isfile(output_file):
            dprint("Output File Exists: ", output_file)
            dprint("Skipping")
            return True

        mkdir(output_file)
        touch(output_file+".inprogress")
        dprint("Strarting transcode for: ",output_file,".inprogress")
        stream.run()
        delete(output_file+".inprogress")
        dprint("Completed transcode for: ",output_file)
        return True
    except Exception as e:
        print('Error: ', e)
        return False
def cleanMovieLibrary():
    for video in movies.search():
        for media in video.media:
            try:
                mres=str(int(media.videoResolution))+"p"
            except Exception as e:
                mres=str(media.videoResolution)
            out=CONFIG["Movie_Clean_Target"]+"/"+video.title+" ("+str(video.year)+")/"+video.title+" ("+str(video.year)+") "+mres+"."+CONFIG["Output_Format"]         
            files=[]
            for part in media.parts:
                fname=part.file
                for pathfilter in CONFIG["Movie_Path_Translation"]:
                    fname=fname.replace(pathfilter[0], pathfilter[1])
                files.append(fname)
            dprint(files, "->", out)
            cat_videos(files, out)
def cleanTVLibrary():
    for show in tv.searchShows():
        for season in show.seasons():
            episodes=season.episodes()
            for ep in episodes:
                for media in ep.media:
                    if ep.episodeNumber > 99:
                        epnum=str(ep.episodeNumber).zfill(3)
                    else:
                        epnum=str(ep.episodeNumber).zfill(2)

                    if season.seasonNumber > 99:
                        snum=str(season.seasonNumber).zfill(3)
                    else:
                        snum=str(season.seasonNumber).zfill(2)
                    try:
                        mres=str(int(media.videoResolution))+"p"
                    except Exception:
                        mres=str(media.videoResolution)
                    out=CONFIG["TV_Clean_Target"]+"/"+show.title+" ("+str(show.year)+") "+mres+"/Season "+str(season.seasonNumber)+"/S"+snum+"E"+epnum+" "+ep.title+"."+CONFIG["Output_Format"]
                    files=[]
                    for part in media.parts:
                        fname=part.file
                        for pathfilter in CONFIG["TV_Path_Translation"]:
                            fname=fname.replace(pathfilter[0], pathfilter[1])
                        files.append(fname)
                    dprint(files, "->", out)
                    cat_videos(files, out)
                    exit()

def printMovieLibrary():
    for video in movies.search():
        for media in video.media:
            dprint(video.title,' - ',video.year,' (',media.videoResolution,')')
            for part in media.parts:
                dprint("    ",part.file.replace(CONFIG["Movie_Path_Translation"][0][0], CONFIG["Movie_Path_Translation"][0][1],1))
def printTVLibrary():
    for show in tv.searchShows():
        dprint(show.title, " - ", show.year,' (', show.seasonCount,')')
        for season in show.seasons():
            episodes=season.episodes()
            dprint('  Season ',season.seasonNumber,' (',len(episodes),')')
            for ep in episodes:
                for media in ep.media:
                    for part in media.parts:
                        dprint('    ',ep.episodeNumber,' - ',ep.title,' (',media.videoResolution,')')
                        dprint('      ',part.file.replace(CONFIG["TV_Path_Translation"][0][0], CONFIG["TV_Path_Translation"][0][1],1))

def mkdir(path):
    # os.path.dirname gets the directory path from the full path
    directory = os.path.dirname(path)

    # os.path.exists checks whether a path already exists
    if not os.path.exists(directory):
        # os.makedirs creates directories recursively
        os.makedirs(directory)
def touch(path):
    with open(path, 'a'):
        os.utime(path, None)
def delete(path):
    try:
        os.remove(path)
        print(f"{path} has been deleted.")
    except FileNotFoundError:
        print(f"The file {path} does not exist.")
    except PermissionError:
        print(f"Permission denied.")
    except Exception as e:
        print(f"An error occurred: {e}")
def copy(src_path, dest_path):
    try:
        shutil.copy2(src_path, dest_path)
        dprint(f"File copied from {src_path} to {dest_path}")
    except IOError as e:
        dprint(f"Unable to copy file. {e}")
    except Exception as e:
        dprint(f"Unexpected error: {e}")

readConfig()
if CONFIG["Features"]["print_movies"]:
    printMovieLibrary()
elif CONFIG["Features"]["print_tv"]:
    printTVLibrary()
elif CONFIG["Features"]["enable_movies"]:
    cleanMovieLibrary()
elif CONFIG["Features"]["enable_tv"]:
    cleanTVLibrary()
