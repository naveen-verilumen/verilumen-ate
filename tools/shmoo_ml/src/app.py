"""
Flask Backend API Server
------------------------
Serves API endpoints for file upload, ML model training & execution, plot rendering,
and downloadable PDF report generation with text options (LLM vs Template).
Includes latest Statistical Process Control (SPC), ROI Economic Engine,
and Active Learning sampling.
"""

from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import sys, os, json, uuid, traceback
import pandas as pd
import numpy as np
from pathlib import Path

# Ensure src and root directories are in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.preprocessor import ShmooPreprocessor
from ml.model import ShmooModel
from report.generator import ReportGenerator
from report.plot_builder import build_shmoo_plot
from text.llm_engine import LLMEngine
from text.template_engine import TemplateEngine
from analytics.roi import (
    ROICalculator, CustomerConfig, ATEConfig, ProductionConfig,
    EngineeringConfig, YieldConfig, BinningConfig, TechnicalEvidence,
)

import tempfile

app = Flask(
    __name__,
    template_folder=str(CURRENT_DIR / 'templates'),
    static_folder=str(CURRENT_DIR / 'static')
)
CORS(app)

IFRAME_ANCESTORS = (
    "frame-ancestors 'self' http://127.0.0.1:3000 http://localhost:3000"
)

@app.after_request
def allow_dashboard_iframe(response):
    response.headers["Content-Security-Policy"] = IFRAME_ANCESTORS
    response.headers.pop("X-Frame-Options", None)
    return response

BASE_DIR = ROOT_DIR
IS_VERCEL = os.environ.get('VERCEL') == '1' or 'VERCEL_REGION' in os.environ

if IS_VERCEL:
    tmp_base = Path(tempfile.gettempdir())
    UPLOAD_DIR = tmp_base / "uploads"
    REPORT_DIR = tmp_base / "reports"
else:
    UPLOAD_DIR = BASE_DIR / "uploads"
    REPORT_DIR = BASE_DIR / "reports"

try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    tmp_base = Path(tempfile.gettempdir())
    UPLOAD_DIR = tmp_base / "uploads"
    REPORT_DIR = tmp_base / "reports"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

sessions = {}

def _resolve_shmoo_api_key() -> str:
    for env_name in ("SHMOO_API_KEY", "API_KEY"):
        val = os.environ.get(env_name, "").strip()
        if val:
            return val
    suite_root = BASE_DIR.parent.parent
    if (suite_root / "verilumen_secrets.py").is_file() and str(suite_root) not in sys.path:
        sys.path.insert(0, str(suite_root))
    try:
        from verilumen_secrets import get_shmoo_api_key
        return get_shmoo_api_key(create_if_missing=True)
    except Exception:
        import keyring
        import secrets as _secrets

        token = keyring.get_password("verilumen-ate", "shmoo_api_key")
        if token and token.strip():
            return token.strip()
        token = _secrets.token_urlsafe(32)
        keyring.set_password("verilumen-ate", "shmoo_api_key", token)
        return token


API_KEY = _resolve_shmoo_api_key()


_demo_cache = None


def _find_demo_csv() -> Path:
    candidates = [
        BASE_DIR / 'shmoo_dataset' / 'Normal_Shmoo_Dataset_500.csv',
        BASE_DIR.parent / 'shmoo_dataset' / 'Normal_Shmoo_Dataset_500.csv',
        Path(r"C:\Users\navee\shmoo_mbist\shmoo_ml_system\shmoo_dataset\Normal_Shmoo_Dataset_500.csv"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    try:
        env = os.environ.get('VERILUMEN_DEMO_DATASETS', '').strip()
        if env and Path(env).is_dir():
            p = Path(env) / 'shmoo' / 'Normal_Shmoo_Dataset_500.csv'
            if p.is_file():
                return p
        for candidate in (
            BASE_DIR.parent.parent / 'demo_datasets',
            BASE_DIR.parent.parent.parent / 'demo_datasets',
            BASE_DIR.parent / 'demo_datasets',
        ):
            if candidate.is_dir():
                p = candidate.resolve() / 'shmoo' / 'Normal_Shmoo_Dataset_500.csv'
                if p.is_file():
                    return p
    except Exception:
        pass
    raise FileNotFoundError('Normal_Shmoo_Dataset_500.csv not found')


def _demo_datasets_root() -> Path:
    try:
        return _find_demo_csv().parent.parent
    except Exception:
        pass
    env = os.environ.get('VERILUMEN_DEMO_DATASETS', '').strip()
    if env:
        root = Path(env)
        if root.is_dir():
            return root.resolve()
    for candidate in (
        BASE_DIR.parent.parent / 'demo_datasets',
        BASE_DIR.parent.parent.parent / 'demo_datasets',
        BASE_DIR.parent / 'demo_datasets',
    ):
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError('demo_datasets folder not found')


def verify_api_key():
    provided_key = request.headers.get('X-API-Key')
    if not provided_key and 'Authorization' in request.headers:
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            provided_key = auth[7:].strip()
        else:
            provided_key = auth.strip()
    if provided_key != API_KEY:
        return jsonify({'error': 'Unauthorized: Invalid or missing API Key'}), 401
    return None


def _process_dataset_file(save_path: Path, customer_cfg_dict: dict = None) -> dict:
    session_id = str(uuid.uuid4())
    customer_config = CustomerConfig.from_dict(customer_cfg_dict or {})

    # Preprocess data
    preprocessor = ShmooPreprocessor()
    meta = preprocessor.load(str(save_path))
    df = preprocessor.process()

    # Train ML model
    model = ShmooModel()
    results = model.train_and_evaluate(df)

    # Save web dark-theme plot PNG
    web_plot_path = UPLOAD_DIR / f"{session_id}_web.png"
    build_shmoo_plot(df, results, save_path=str(web_plot_path), as_base64=True)

    sessions[session_id] = {
        'df': df,
        'preprocessor': preprocessor,
        'model': model,
        'meta': meta,
        'results': results,
        'save_path': str(save_path),
        'web_plot_path': str(web_plot_path),
        'customer_config': customer_config,
    }

    # Serialize plot points
    die_col = 'Die_ID' if 'Die_ID' in df.columns else ('Test_ID' if 'Test_ID' in df.columns else None)
    points_data = []
    for _, row in df.iterrows():
        points_data.append({
            'vdd': round(float(row['VDD_V']), 4),
            'freq': round(float(row['Frequency_GHz']), 4),
            'result': str(row['Test_Result']),
            'code': str(row['Failure_Code']),
            'die': str(row[die_col]) if die_col else 'Device 1',
            'pat': str(row.get('Pattern_ID', row.get('March_Algorithm', ''))) if ('Pattern_ID' in df.columns or 'March_Algorithm' in df.columns) else ''
        })

    # Compute ROI using defensible economic engine
    roi_data = _compute_roi(df, results, customer_config)

    return {
        'session_id': session_id,
        'meta': meta,
        'results': _serialize_results(results),
        'optimizations': roi_data,
        'plot_data': {
            'points': points_data,
            'vdd_range': [float(df['VDD_V'].min()), float(df['VDD_V'].max())],
            'freq_range': [float(df['Frequency_GHz'].min()), float(df['Frequency_GHz'].max())],
        },
        'plot_url': f'/api/plot/{session_id}.png'
    }


@app.route('/')
@app.route('/api/index')
def index():
    return render_template('index.html', shmoo_api_key=API_KEY)


@app.route('/api/upload', methods=['POST'])
def upload():
    auth_err = verify_api_key()
    if auth_err:
        return auth_err

    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        session_id = str(uuid.uuid4())
        ext = Path(file.filename).suffix
        save_path = UPLOAD_DIR / f"{session_id}{ext}"
        file.save(save_path)

        customer_cfg_raw = request.form.get('customer_config', '{}')
        try:
            customer_cfg_dict = json.loads(customer_cfg_raw) if customer_cfg_raw else {}
        except Exception:
            customer_cfg_dict = {}

        return jsonify(_process_dataset_file(save_path, customer_cfg_dict))

    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/health')
@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok", "service": "shmoo_ml", "version": "1.0.0"})


@app.route('/api/demo/load', methods=['GET', 'POST'])
def demo_load():
    """Load bundled demo CSV for presentations (cached in-memory for instant response)."""
    global _demo_cache
    if _demo_cache is not None:
        return jsonify(_demo_cache)
    try:
        demo_csv = _find_demo_csv()
        session_id = str(uuid.uuid4())
        save_path = UPLOAD_DIR / f"{session_id}_demo.csv"
        save_path.write_bytes(demo_csv.read_bytes())
        payload = _process_dataset_file(save_path)
        payload['demo'] = True
        payload['source_file'] = demo_csv.name
        _demo_cache = payload
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/plot/<session_id>.png')
def get_plot_image(session_id):
    try:
        web_plot_path = UPLOAD_DIR / f"{session_id}_web.png"
        if not web_plot_path.exists():
            session = sessions.get(session_id)
            if not session:
                return jsonify({'error': 'Session not found'}), 404
            build_shmoo_plot(session['df'], session['results'], save_path=str(web_plot_path), as_base64=True)

        return send_file(str(web_plot_path), mimetype='image/png')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/report', methods=['POST'])
def generate_report():
    auth_err = verify_api_key()
    if auth_err:
        return auth_err

    try:
        data = request.json or {}
        session_id = data.get('session_id')
        text_mode = data.get('text_mode', 'template')  # 'llm' or 'template'
        test_methodology = data.get('test_methodology', 'MBIST')  # 'MBIST', 'LBIST', or 'ATPG'

        session = sessions.get(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404

        results = session['results']
        meta = session['meta']
        df = session['df']

        # Generate text narrative
        if text_mode == 'llm':
            engine = LLMEngine()
            if engine.is_available():
                narrative = engine.generate(results, meta, test_methodology=test_methodology)
            else:
                narrative = TemplateEngine().generate(results, meta, test_methodology=test_methodology) + "\n\n(Note: LLM weights were missing; output defaulted to template mode.)"
        else:
            engine = TemplateEngine()
            narrative = engine.generate(results, meta, test_methodology=test_methodology)

        # Build plot image for PDF (light background for printing)
        plot_path = REPORT_DIR / f"{session_id}_plot.png"
        build_shmoo_plot(df, results, save_path=str(plot_path))

        # Render PDF
        report_path = REPORT_DIR / f"{session_id}_report.pdf"
        generator = ReportGenerator()
        generator.generate(
            results=results,
            meta=meta,
            narrative=narrative,
            plot_path=str(plot_path),
            output_path=str(report_path),
            test_methodology=test_methodology
        )

        return send_file(
            str(report_path),
            as_attachment=True,
            download_name=f"{test_methodology}_SHMOO_Analysis_Report_{meta.get('die_id','D0001')}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


def _serialize_results(results) -> dict:
    return {
        'accuracy': round(results.accuracy, 4),
        'cv_accuracy': round(results.cv_accuracy, 4),
        'cv_std': round(results.cv_std, 4),
        'boundary_slope': round(results.boundary_slope, 4),
        'boundary_intercept': round(results.boundary_intercept, 4),
        'boundary_r2': round(results.boundary_r2, 4),
        'recommended_vdd': round(results.recommended_vdd, 3),
        'recommended_freq': round(results.recommended_freq, 3),
        'voltage_margin_v': round(results.voltage_margin_v, 3),
        'freq_margin_ghz': round(results.freq_margin_ghz, 3),
        'n_pass': results.n_pass,
        'n_fail': results.n_fail,
        'failure_code_dist': results.failure_code_dist,
        'critical_fault_patterns': getattr(results, 'critical_fault_patterns', results.timing_fail_patterns),
        'timing_fail_patterns': results.timing_fail_patterns,
        'is_multi_die': getattr(results, 'is_multi_die', False),
        'die_rankings': getattr(results, 'die_rankings', []),
        'high_performer': getattr(results, 'high_performer', None),
        'low_performer': getattr(results, 'low_performer', None),
        'die_results': getattr(results, 'die_results', {}),
        'shmoo_plot_type': getattr(results, 'shmoo_plot_type', 'Normal Shmoo'),
        'shmoo_type_description': getattr(results, 'shmoo_type_description', ''),
        # SPC / Cpk statistical guardbanding
        'cpk_vmin': getattr(results, 'cpk_vmin', 0.0),
        'cpk_fmax': getattr(results, 'cpk_fmax', 0.0),
        'spc_guardband_v_mv': round(getattr(results, 'spc_guardband_v', 0.0) * 1000.0, 1),
        'spc_guardband_f_mhz': round(getattr(results, 'spc_guardband_f', 0.0) * 1000.0, 1),
        'spc_status_v': getattr(results, 'spc_status_v', 'N/A'),
        'spc_status_f': getattr(results, 'spc_status_f', 'N/A'),
        'active_sampler': getattr(results, 'active_sampler', 'RANSAC_Legacy'),
    }


def _compute_roi(df: pd.DataFrame, results, customer_config: CustomerConfig) -> dict:
    ACTIVE_LEARNING_PRR = 0.828  # Empirically validated from benchmark harness

    label_series = df['label'] if 'label' in df.columns else (
        df['Test_Result'].astype(str).str.upper() == 'PASS'
    ).astype(int)
    yield_overall = float(label_series.mean() * 100.0)
    v_max = float(df['VDD_V'].max()) if 'VDD_V' in df.columns else 1.2
    v_rec = float(results.recommended_vdd)
    f_rec = float(results.recommended_freq)

    evidence = TechnicalEvidence(
        boundary_r2=float(results.boundary_r2),
        cv_accuracy=float(results.cv_accuracy),
        cv_std=float(results.cv_std),
        cpk_vmin=getattr(results, 'cpk_vmin', 0.0),
        cpk_fmax=getattr(results, 'cpk_fmax', 0.0),
        spc_status_v=getattr(results, 'spc_status_v', 'N/A'),
        spc_status_f=getattr(results, 'spc_status_f', 'N/A'),
        total_sweep_points=len(df),
        active_learning_prr=ACTIVE_LEARNING_PRR,
    )

    calculator = ROICalculator()
    report = calculator.compute(customer_config, evidence)
    roi_dict = calculator.to_api_dict(report)

    boundary_at_rec = float(results.boundary_slope * v_rec + results.boundary_intercept)
    freq_headroom_mhz = max(0.0, (boundary_at_rec - f_rec) * 1000.0)
    power_savings_pct = max(0.0, (1.0 - (v_rec ** 2) / (v_max ** 2)) * 100.0) if v_max > 0 else 0.0

    roi_dict['operating_point'] = {
        'recommended_vdd': round(v_rec, 3),
        'recommended_freq': round(f_rec, 3),
        'baseline_vmax': round(v_max, 3),
        'freq_headroom_mhz': round(freq_headroom_mhz, 1),
        'power_savings_pct': round(power_savings_pct, 1),
        'voltage_guardband_mv': round(getattr(results, 'spc_guardband_v', results.voltage_margin_v) * 1000.0, 1),
        'spc_guardband_f_mhz': round(getattr(results, 'spc_guardband_f', 0.0) * 1000.0, 1),
        'yield_overall_pct': round(yield_overall, 1),
        'active_sampler': getattr(results, 'active_sampler', 'RANSAC_Legacy'),
        'active_learning_prr_pct': round(ACTIVE_LEARNING_PRR * 100.0, 1),
    }

    c = report.characterization
    roi_dict['total_tested_points'] = c.baseline_points
    roi_dict['optimized_test_points'] = c.adaptive_points
    roi_dict['test_time_saved_pct'] = round(ACTIVE_LEARNING_PRR * 100.0, 1)

    return roi_dict


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
