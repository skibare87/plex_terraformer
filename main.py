#!/usr/bin/python3
import os
import sys
import time
import requests
from plexapi.server import PlexServer
from plexapi.library import LibrarySection
import ffmpeg

DEBUG=True
MAX_RES=1080
#OPTIMIZE={'vcodec':'libx264', 'acodec':'aac', 'crf':25, 'preset':'medium'}
OPTIMIZE={'vcodec':'h264_nvenc', 'acodec':'aac', 'crf':25, 'preset':'medium'}

MAX_CONV=10
LAST_CONVERTED=""

PLEX_TOKEN="3h-5sBLp8emCqNK39wq5"
PLEX_IP="192.168.1.79"
PLEX_PORT="32400"
plex=PlexServer("http://192.168.1.79:32400", PLEX_TOKEN)


MOVIEDIR="/mnt/p/video/download"
MCLEAN_DIR="/mnt/z/cleaned/movies"
MTRANS=[["/data/video","/mnt/p/video"],["/data/kvideo","/mnt/p/remotefs/Konstantin/video"]]
movies=plex.library.section('Movies')


TVDIR="/mnt/p/video/downloadtv"
TCLEAN_DIR="/mnt/z/cleaned/tv"
TTRANS=MTRANS
tv=plex.library.section('TV Shows')

def dprint(*names):
    if DEBUG:
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

def convert_video(input_file, output_file):
    try:
        probe = ffmpeg.probe(input_file)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream is None:
            print('No video stream found')
            return
        if 'h264' in video_stream['codec_name']:
            hwdecode={"hwaccel":'cuvid', 'c:v':'h264_cuvid'}
        elif 'hevc' in  video_stream['codec_name']:
            hwdecode={"hwaccel":'cuvid', 'c:v':'hevc_cuvid'}
        else:
            hwdecode={}
        width = int(video_stream['width'])
        height = int(video_stream['height'])

        if height > MAX_RES:
            # Downscale video to 1080p if above this resolution
            aspect_ratio = width / height
            height = MAX_RES
            width = int(aspect_ratio * height)
            stream = ffmpeg.input(input_file,**hwdecode).output(output_file, vf='scale=%d:%d' % (width, height), **OPTIMIZE)
        else:
            # Keep the original resolution if it's 1080p or below
            stream = ffmpeg.input(input_file,**hwdecode).output(output_file, **OPTIMIZE)
        safeRunStream(stream, output_file)
    except Exception as err:
        print(f"Unexpected {err=}, {type(err)=}") 
def cat_videos(video_files, output_file):
    if len(video_files) < 1:
        return
    elif len(video_files) == 1:
        return convert_video(video_files[0], output_file)
    try:
        input_streams = [ffmpeg.input(file) for file in video_files]
        probe = ffmpeg.probe(video_files[0])
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream is None:
            print('No video stream found')
            return
        if 'h264' in video_stream['codec_name']:
            hwdecode={"hwaccel":'cuvid', 'c:v':'h264_cuvid'}
        elif 'hevc' in  video_stream['codec_name']:
            hwdecode={"hwaccel":'cuvid', 'c:v':'hevc_cuvid'}
        else:
            hwdecode={}
        width = int(video_files[0]['width'])
        height = int(video_files[0]['height'])

        if height > MAX_RES:
            # Downscale video to 1080p if above this resolution
            aspect_ratio = width / height
            height = MAX_RES
            width = int(aspect_ratio * height)
            stream=ffmpeg.concat(*input_streams, v=1, a=1,**hwdecode).output(output_file, vf='scale=%d:%d' % (width, height), **OPTIMIZE)
        else:
            # Keep the original resolution if it's 1080p or below
            stream=ffmpeg.concat(*input_streams, v=1, a=1, **hwdecode).output(output_file, vf='scale=%d:%d' % (width, height), **OPTIMIZE)
        safeRunStream(stream,output_file)
    except Exception as e:
        print('Error: ', e)
def safeRunStream(stream, output_file):
    if os.path.isfile(output_file) and not os.path.isfile(output_file+".inprogress"):
        dprint("Output File Exists: ", output_file)
        dprint("Skipping")
        return
    else:
        dprint("Detected incomplete transcode: ",output_file,".inprogress")
        dprint("Removing files and retrying")
        delete(output_file)
        delete(output_file+".inprogress")

    mkdir(output_file)
    touch(output_file+".inprogress")
    dprint("Strarting transcode for: ",output_file,".inprogress")
    stream.run()
    delete(output_file)
    dprint("Completed transcode for: ",output_file)
def cleanMovieLibrary():
    for video in movies.search():
        for media in video.media:
            out=MCLEAN_DIR+"/"+video.title+" ("+str(video.year)+") "+str(media.videoResolution)+"p.mkv"         
            files=[]
            for part in media.parts:
                fname=part.file
                for pathfilter in MTRANS:
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
                    out=TCLEAN_DIR+"/"+show.title+" ("+str(show.year)+") "+str(media.videoResolution)+"p/Season "+str(season.seasonNumber)+"/S"+snum+"E"+epnum+" "+ep.title+".mkv"
                    files=[]
                    for part in media.parts:
                        fname=part.file
                        for pathfilter in TTRANS:
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
                dprint("    ",part.file.replace(MTRANS[0][0], MTRANS[0][1],1))
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
                        dprint('      ',part.file.replace(TTRANS[0][0], TTRANS[0][1],1))

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
cleanMovieLibrary()
#get_video_codec('/mnt/p/video/Bollywood/3 Idiots (2009)/3 Idiots (2009) Bluray-1080p.mp4')
#get_video_codec('/mnt/p/remotefs/Konstantin/video/downloadtv/2.Broke.Girls/2.Broke.Girls.2011.S05.1080p.AMZN.WEB-DL.x265.10bit.RZeroX/2 Broke Girls (2011) - S05E20 - And the Partnership Hits the Fan (1080p AMZN WEB-DL x265 RZeroX).mkv')
#convert_video('/mnt/p/remotefs/Konstantin/video/downloadtv/2.Broke.Girls/2.Broke.Girls.2011.S05.1080p.AMZN.WEB-DL.x265.10bit.RZeroX/2 Broke Girls (2011) - S05E20 - And the Partnership Hits the Fan (1080p AMZN WEB-DL x265 RZeroX).mkv','/mnt/c/Users/matt/output.mkv')
#printMovieLibrary()
#printTVLibrary()

