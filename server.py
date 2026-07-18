from flask import Flask, jsonify, request, render_template_string
import time


app = Flask(__name__)

trail_points = []
known_point_ids = set()

MAX_TRAIL_POINTS = 10000


def normalise_point(data):
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        raise ValueError("Missing latitude or longitude")

    point_id = str(
        data.get("point_id")
        or f"{data.get('device', 'mappi')}-{data.get('timestamp', time.time())}"
    )

    return {
        "point_id": point_id,
        "device": data.get("device", "mappi"),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "timestamp": float(data.get("timestamp", time.time())),
        "speed_knots": data.get("speed_knots"),
        "course": data.get("course"),
    }


def store_point(point):
    global trail_points

    if point["point_id"] in known_point_ids:
        return False

    trail_points.append(point)
    known_point_ids.add(point["point_id"])

    trail_points.sort(key=lambda item: item["timestamp"])

    if len(trail_points) > MAX_TRAIL_POINTS:
        removed = trail_points[:-MAX_TRAIL_POINTS]
        trail_points = trail_points[-MAX_TRAIL_POINTS:]

        for old_point in removed:
            known_point_ids.discard(old_point["point_id"])

    return True


@app.route("/")
def map_page():
    return render_template_string("""
    <!-- Keep your current Leaflet HTML, CSS and JavaScript here. -->

    <!-- The map JavaScript should request /trail: -->

    <script>
        async function updateMap() {
            const response = await fetch("/trail");
            const data = await response.json();

            const latest = data.latest;
            const trail = data.trail || [];

            const trailLatLngs = trail.map(point => [
                Number(point.latitude),
                Number(point.longitude)
            ]);

            // Update your existing Leaflet polyline and marker here.
        }
    </script>
    """)


@app.route("/location", methods=["GET"])
def location():
    latest = trail_points[-1] if trail_points else None
    return jsonify(latest)


@app.route("/trail", methods=["GET"])
def trail():
    latest = trail_points[-1] if trail_points else {
        "device": "mappi",
        "latitude": None,
        "longitude": None,
        "timestamp": None,
    }

    return jsonify({
        "latest": latest,
        "trail": trail_points,
        "count": len(trail_points),
    })


@app.route("/update-location", methods=["POST"])
def update_location():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "No JSON received"}), 400

    try:
        point = normalise_point(data)
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400

    added = store_point(point)

    return jsonify({
        "status": "ok",
        "added": added,
        "point_id": point["point_id"],
        "trail_points": len(trail_points),
    })


@app.route("/upload-trail", methods=["POST"])
def upload_trail():
    data = request.get_json(silent=True) or {}
    points = data.get("points", [])

    if not isinstance(points, list):
        return jsonify({"error": "points must be a list"}), 400

    accepted_ids = []
    added_count = 0
    errors = []

    for index, raw_point in enumerate(points):
        try:
            point = normalise_point(raw_point)
            added = store_point(point)

            accepted_ids.append(point["point_id"])

            if added:
                added_count += 1

        except (TypeError, ValueError) as error:
            errors.append({
                "index": index,
                "error": str(error),
            })

    return jsonify({
        "status": "ok",
        "received": len(points),
        "added": added_count,
        "accepted_ids": accepted_ids,
        "errors": errors,
        "trail_points": len(trail_points),
    })


@app.route("/clear-trail", methods=["POST"])
def clear_trail():
    trail_points.clear()
    known_point_ids.clear()

    return jsonify({
        "status": "ok",
        "trail_points": 0,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
