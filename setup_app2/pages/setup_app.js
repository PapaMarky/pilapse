
function set_exposure_time() {
    var exposure_time = document.getElementById("exposure_time").value,
        xhttp = new XMLHttpRequest();
    console.log(exposure_time)
    xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
           // Typical action to be performed when the document is ready:
           console.log(xhttp.responseText);
        }
    };
    xhttp.open("GET", "set_control?name=ExposureTime&value="+exposure_time, true);
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