#!/bin/bash
# H.264 HLS of the BlueStacks screen at the device's native frame rate (~30fps).
# screenrecord caps at 180s, so loop it and feed one continuous H.264 stream to ffmpeg.
# Deps: adb, ffmpeg. Served by live_stream.py over the same cloudflare tunnel.
set -u
cd "$(dirname "$0")"
D=127.0.0.1:5555
SIZE=${SIZE:-720x1280}
BR=${BR:-6000000}
mkdir -p hls
rm -f hls/*.ts hls/*.m3u8

( while true; do
    adb -s "$D" exec-out screenrecord --output-format=h264 --size "$SIZE" \
        --bit-rate "$BR" --time-limit 175 - 2>/dev/null || true
    sleep 0.2
  done ) | ffmpeg -hide_banner -loglevel error \
      -use_wallclock_as_timestamps 1 -fflags +genpts -f h264 -i - \
      -c:v libx264 -preset ultrafast -tune zerolatency \
      -g 30 -keyint_min 30 -sc_threshold 0 -pix_fmt yuv420p \
      -f hls -hls_time 1 -hls_list_size 8 \
      -hls_flags delete_segments+append_list+omit_endlist+independent_segments \
      -hls_segment_type mpegts \
      -hls_segment_filename hls/seg_%05d.ts hls/stream.m3u8
