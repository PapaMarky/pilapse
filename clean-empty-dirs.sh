PATH=$1

if [[ -z $PATH ]]; then PATH=~; fi

/usr/bin/find $PATH -empty -type d -delete
