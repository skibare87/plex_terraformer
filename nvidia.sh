#!/bin/bash
CWD=`pwd`
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda build-essential yasm cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev
mkdir -p nvidia/ && cd nvidia/
git clone https://git.videolan.org/git/ffmpeg/nv-codec-headers.git
cd nv-codec-headers && sudo make install
cd $CWD
