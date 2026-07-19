#!/bin/bash
# H.264 HLS stream of the BlueStacks screen, served over the existing cloudflare tunnel.
# Deps: adb, ffmpeg, cloudflared (all already present). No accounts.
set -e
cd "$(dirname "$0")"
D=127.0.0.1:5555
mkdir -p hls
rm -f hls/*.ts hls/*.m3u8

# screenrecord caps at ~3min, so loop it and feed one continuous H.264 stream to ffmpeg.
( while true; do
    adb -s $D exec-out screenrecord --output-format=h264 --time-limit 170 --bit-rate 4000000 - || true
  done ) | ffmpeg -hide_banner -loglevel warning -fflags nobuffer \
      -f h264 -i - \
      -c:v copy \
      -f hls -hls_time 1 -hls_list_size 6 \
      -hls_flags delete_segments+append_list+omit_endlist \
      -hls_segment_filename hls/seg_%05d.ts hls/stream.m3u8
