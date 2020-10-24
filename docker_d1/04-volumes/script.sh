#!/usr/bin/env bash

docker build -t step04:volume .
docker run --mount type=bind,source="$(pwd)"/resources/,target=/data,readonly step04:volume

