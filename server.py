from pathlib import Path
import json
import os
import subprocess

from flask import Flask, request, jsonify, send_from_directory

BASE = Path(__file__).resolve().parent
AGENDAS = BASE / "Agendas"
JSON_DIR = BASE / "Agendas-json"
MAIN = BASE / "main.py"

# Webhook do Make.
WEBHOOK_URL = os.getenv(
    "DISPAROS_WEBHOOK_URL",
    "https://hook.us2.make.com/ndrob044e6fk1ka7hwvwphgish5e9rrp",
)

AGENDAS.mkdir(exist_ok=True)
JSON_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(BASE), static_url_path="")


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.post("/api/processar-agenda")
def processar_agenda():
    arquivo = request.files.get("arquivo")

    if not arquivo or not arquivo.filename:
        return jsonify({"erro": "Nenhum arquivo foi enviado."}), 400

    if not arquivo.filename.lower().endswith(".pdf"):
        return jsonify({"erro": "O arquivo precisa ser PDF."}), 400

    destino = AGENDAS / "agenda.pdf"
    arquivo.save(destino)

    if not MAIN.exists():
        return jsonify({"erro": f"main.py não encontrado em: {MAIN}"}), 500

    try:
        result = subprocess.run(
            ["python", str(MAIN)],
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return jsonify({
            "erro": "main.py excedeu o tempo limite de 5 minutos.",
            "etapa": "processamento",
        }), 500

    if result.returncode != 0:
        return jsonify({
            "erro": "main.py terminou com erro.",
            "etapa": "processamento",
            "detalhes": result.stderr[-4000:],
        }), 500

    json_path = JSON_DIR / "agenda.json"
    if not json_path.exists():
        return jsonify({
            "erro": "main.py executou, mas Agendas-json/agenda.json não foi encontrado.",
            "etapa": "conferência",
            "saida": result.stdout[-4000:],
        }), 500

    try:
        with json_path.open("r", encoding="utf-8") as f:
            agenda = json.load(f)
    except Exception as exc:
        return jsonify({
            "erro": f"Não foi possível ler agenda.json: {exc}",
            "etapa": "conferência",
        }), 500

    return jsonify({
        "ok": True,
        "agenda": agenda,
        "etapa": "conferência",
        "mensagem": "Agenda processada e pronta para disparo.",
    })


@app.post("/api/disparar")
def disparar():
    payload = request.get_json(silent=True) or {}
    agenda = payload.get("agenda", [])

    if not isinstance(agenda, list) or not agenda:
        return jsonify({"erro": "Agenda vazia.", "etapa": "validação"}), 400

    try:
        import requests
    except ImportError:
        return jsonify({
            "erro": "A dependência 'requests' não está instalada. Execute: pip install flask requests",
            "etapa": "webhook",
        }), 500

    try:
        r = requests.post(
            WEBHOOK_URL,
            json={"agenda": agenda},
            timeout=30,
        )
        r.raise_for_status()
        return jsonify({
            "ok": True,
            "status_webhook": r.status_code,
            "quantidade": len(agenda),
            "etapa": "finalização",
            "mensagem": "Webhook aceitou o disparo.",
        })
    except Exception as exc:
        return jsonify({
            "erro": f"Falha no webhook: {exc}",
            "etapa": "webhook",
        }), 502


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
