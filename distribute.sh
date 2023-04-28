for host in picam001 picam002 bigpi; do
    echo "Rsyncing to $host"
    rsync -avzh . pi@${host}.local:./pilapse/
done

	    
