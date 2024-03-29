function set_exposure_time() {
    var exposure_time = document.getElementById("exposure_time").value,
        zoom = document.getElementById("zoom").value,
        analog_gain = document.getElementById("analog_gain").value,
        locked = document.getElementById("locksettings").checked,
        xhttp = new XMLHttpRequest();
    if (locked) {
        alert('Settings Are Locked');
        return;
    }
    console.log(exposure_time)
    document.getElementById("img_label").innerHTML = 'Loading...'
    xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
           // Typical action to be performed when the document is ready:
           console.log(xhttp.responseText);
           document.getElementById("latest_img").src = xhttp.responseText
           document.getElementById("img_label").innerHTML = xhttp.responseText
        }
    };
    xhttp.open("GET", "set_exposure?exp=" + exposure_time + "&zoom=" + zoom + "&gain=" + analog_gain, true);
    xhttp.send();
}

function start_image_loop() {
    console.log("starting autoload image loop")
    setInterval(do_autoload, 3000)
}

function do_autoload() {
    if (! document.getElementById("autoload").checked) {
        //console.log("autoload: disabled")
        return
    }
    //console.log('autoload: enabled')
    update_image()
}

function singleshot() {
    var xhttp = new XMLHttpRequest();

    console.log("requesting singleshot")

    document.getElementById("img_label").innerHTML = 'Requesting Singleshot...';

    xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
           // Typical action to be performed when the document is ready:
           console.log(xhttp.responseText);
        }
    };
    xhttp.open("GET", "singleshot", true);
    xhttp.send();
}

function update_image() {
    var xhttp = new XMLHttpRequest()
    console.log("update_image")
    document.getElementById("img_label").innerHTML = 'Loading...'
    xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
           // Typical action to be performed when the document is ready:
           console.log(xhttp.responseText);
           document.getElementById("latest_img").src = xhttp.responseText
           document.getElementById("img_label").innerHTML = xhttp.responseText
        }
    };
    xhttp.open("GET", "get_latest", true);
    xhttp.send();
}

function zoom_changed() {
    var xhttp = new XMLHttpRequest(),
        new_zoom = document.getElementById("zoom").value;
    console.log('new zoom: ' + new_zoom)
    xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
           // Typical action to be performed when the document is ready:
           console.log(xhttp.responseText);
        }
    };
    xhttp.open("GET", "set_zoom?zoom=" + new_zoom, true);
    xhttp.send();

}