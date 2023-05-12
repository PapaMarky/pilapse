hostlist=$@

if [[ -z $hostlist ]]; then
  hostlist="picam001 picam002 picam003 bigpi"
fi

for host in $hostlist; do
    echo "Rsyncing to $host"
    rsync -avzh . pi@${host}.local:./pilapse/
done

	    
