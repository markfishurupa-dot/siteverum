# Survey contract (working draft)

Native v1.3 logs contain timestamp_utc, video_elapsed_ms, recording_start_utc_ms, lat, lon, accuracy_m, speed_mps, bearing, alt_m. Times are milliseconds. Elapsed is callback time relative to the recorder-start anchor; it is not proof of exposure or GPS fix time. Pair source basenames, not archive names. Exports must use relative image paths and contain no points without readable images.
