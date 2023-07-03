function set_exposure_time() {
    var exposure_time = document.getElementById("exposure_time").value,
        pid = document.getElementById("pid").value,
        zoom = document.getElementById("zoom").value,
        xhttp = new XMLHttpRequest();
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
    xhttp.open("GET", "set_exposure?exp=" + exposure_time + "&pid=" + pid + "&zoom=" + zoom, true);
    xhttp.send();
}

function start_image_loop() {
    console.log("starting update image loop")
    setInterval(update_image, 10000)
}
function update_image() {
    var xhttp = new XMLHttpRequest();
    console.log('update_image')
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