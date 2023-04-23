for host in picam001 picam002 bigpi; do
    echo "Uploading to $host"
    scp ./pilapse.py pi@${host}.local:.
done

	    
