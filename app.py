from flask import Flask, render_template, request, redirect, url_for, flash
import os
import subprocess

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', 'change-me')

# Path to project root (where docker-compose.yml lives)
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(CONFIG_DIR, '.env')

@app.route('/', methods=['GET', 'POST'])
def index():
    # Load existing config from .env
    config = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    config[key] = val

    if request.method == 'POST':
        # Save new config back to .env
        new_config = {
            'TG_API_ID': request.form['TG_API_ID'],
            'TG_API_HASH': request.form['TG_API_HASH'],
            'TG_TARGET': request.form['TG_TARGET'],
            'TG_REPLY_TEXT': request.form['TG_REPLY_TEXT'],
        }
        with open(ENV_PATH, 'w') as f:
            for k, v in new_config.items():
                f.write(f"{k}={v}\n")

        # Redeploy the entire compose stack
        subprocess.run([
            'docker', 'compose', 'up', '-d', '--build'
        ], cwd=CONFIG_DIR, check=True)

        flash('Configuration updated and container restarted!', 'success')
        return redirect(url_for('index'))

    return render_template('index.html', config=config)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
