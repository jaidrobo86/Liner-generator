import io
import os
from flask import Flask, render_template, request, send_file, jsonify
from liner_generator import draw_liner_pdf, FABRIC_SPECS

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", fabric_refs=list(FABRIC_SPECS.keys()))


@app.route("/generate", methods=["POST"])
def generate():
    try:
        diameter_m = float(request.form["diameter"])
        fabric_ref = request.form["fabric_ref"]
        mode       = request.form["mode"]
        client     = request.form.get("client", "").strip()
        project    = request.form.get("project", "").strip()

        if diameter_m <= 0 or diameter_m > 500:
            return jsonify({"error": "Diameter must be between 0 and 500 m"}), 400
        if fabric_ref not in FABRIC_SPECS:
            return jsonify({"error": "Invalid fabric reference"}), 400
        if mode not in ("individual", "prefab"):
            return jsonify({"error": "Invalid mode"}), 400

        buf = io.BytesIO()
        draw_liner_pdf(
            diameter_m  = diameter_m,
            fabric_ref  = fabric_ref,
            mode        = mode,
            client      = client,
            project     = project,
            output_path = buf,
        )
        buf.seek(0)

        filename = f"{diameter_m}m_{fabric_ref}_{mode}.pdf"
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    except ValueError:
        return jsonify({"error": "Invalid diameter value"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
