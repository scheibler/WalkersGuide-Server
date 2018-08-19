#!/bin/bash


# helper functions

# timestamp
get_timestamp() {
    year=$(date +%Y)
    month=$(date +%m)
    day=$(date +%d)
    hour=$(date +%H)
    minute=$(date +%M)
    second=$(date +%S)
    echo "$hour:$minute:$second $year.$month.$day"
}

get_current_date() {
    year=$(date +%Y)
    month=$(date +%m)
    day=$(date +%d)
    echo "$year-$month-$day"
}

