"""
HDU Remote Judge - 完整简体中文 Flask Demo with styled verdicts和编译信息处理
"""

from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup
import time
import html

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-in-prod'

HDU_BASE = "http://acm.hdu.edu.cn"

INDEX_HTML = '''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>HDU远端评测</title>
<style>
body{font-family: Arial; max-width:900px;margin:40px auto;padding:0 20px;}
label,input,select,textarea,button{display:block;margin-bottom:10px;width:100%;}
textarea{height:300px;font-family: monospace;}
button{padding:8px; background:#4CAF50; color:white; border:none; cursor:pointer;}
button:hover{background:#45a049;}
</style>
</head>
<body>
<h2>HDU远端评测</h2>
<form method="post" action="/submit">
<label>PHPSESSID: <input name="phpsessid" type="text" required></label>
<label>用户名: <input name="username" type="text" required></label>
<label>题目ID: <input name="problem_id" type="text" required></label>
<label>语言:
<select name="language">
<option value="0">G++</option>
<option value="1">GCC</option>
<option value="2">Java</option>
<option value="3">Pascal</option>
</select></label>
<label>源代码:<br><textarea name="source" required></textarea></label>
<button type="submit">提交</button>
</form>
</body>
</html>
'''

RESULT_HTML = '''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>提交结果</title>
<style>
body{font-family: Arial; max-width:900px;margin:40px auto;padding:0 20px;}
.result{padding:10px;border-radius:5px; margin:5px 0; font-weight:bold;}
.ac{background:#d4edda;color:#155724;border:1px solid #c3e6cb;}
.wa{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;}
.ce{background:#fff3cd;color:#856404;border:1px solid #ffeeba;}
.tle{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;}
.mle{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;}
.re{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;}
</style>
</head>
<body>
<h2>提交结果</h2>
<div><strong>题目:</strong> {{problem}}</div>
<div><strong>RunID:</strong> {{runid}}</div>
<div class="result {{verdict|lower}}">判定结果: {{verdict}}</div>
<div><strong>用时:</strong> {{time}} &nbsp; <strong>内存:</strong> {{memory}}</div>
<div><strong>语言:</strong> {{language}}</div>
{% if compile_info %}
<h3>编译信息</h3>
<pre>{{compile_info}}</pre>
{% endif %}
<h3>原始状态行</h3>
<pre>{{raw_row}}</pre>
<p><a href="/">返回首页</a></p>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/submit', methods=['POST'])
def submit():
    phpsessid = request.form.get('phpsessid')
    username = request.form.get('username')
    problem_id = request.form.get('problem_id')
    language = request.form.get('language') or '0'
    source = request.form.get('source')

    session = requests.Session()
    session.cookies.set('PHPSESSID', phpsessid, domain='acm.hdu.edu.cn')

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': f'{HDU_BASE}/submit.php',
        'Origin': HDU_BASE
    }

    submit_endpoint = f'{HDU_BASE}/submit.php?action=submit'
    session.post(submit_endpoint, data={'problemid': problem_id, 'language': language, 'usercode': source}, headers=headers)

    status_url = f'{HDU_BASE}/status.php?user={username}&pid={problem_id}'
    interval = 1.0
    max_wait = 60.0
    waited = 0.0
    parsed = None

    while waited < max_wait:
        sresp = session.get(status_url, headers=headers)
        sresp.encoding = 'gb2312'
        parsed = parse_status_table(sresp.text, username, problem_id)
        if parsed:
            result_lower = parsed['result'].lower()
            if any(k in result_lower for k in ['accept','ac']): verdict='AC'; break
            if any(k in result_lower for k in ['wrong answer','wa']): verdict='WA'; break
            if any(k in result_lower for k in ['compile error','compilation error']): verdict='CE'; break
            if any(k in result_lower for k in ['tle','time limit']): verdict='TLE'; break
            if any(k in result_lower for k in ['mle', 'memory', 'memory limit']): verdict = 'MLE'; break
            if any(k in result_lower for k in ['runtime', 're']): verdict = 'RE'; break
        time.sleep(interval)
        waited += interval
        interval = min(interval*1.8, 8.0)

    if not parsed:
        return f"<p>无法解析状态，请稍后重试。<a href='/'>返回首页</a></p>"

    runid = parsed.get('runid')
    compile_info = fetch_compile_info(session, runid, headers) if runid else ''

    return render_template_string(RESULT_HTML,
                                  problem=parsed.get('problem'),
                                  runid=runid,
                                  verdict=verdict,
                                  time=parsed.get('time'),
                                  memory=parsed.get('memory'),
                                  language=parsed.get('language'),
                                  compile_info=compile_info,
                                  raw_row=parsed.get('raw_html'))

# --- parse_status_table updated for HDUOJ ---

def parse_status_table(html_text, username, problem_id):
    soup = BeautifulSoup(html_text, 'html.parser')
    rows = soup.find_all('tr')
    for r in rows[1:]:
        cols = r.find_all('td')
        if len(cols) < 9: continue
        runid = cols[0].get_text(strip=True)
        judge_status = cols[2].get_text(strip=True)
        problem_col = cols[3].find('a')
        problem_val = problem_col.get_text(strip=True) if problem_col else cols[3].get_text(strip=True)
        author_col = cols[8].find('a')
        author_val = author_col.get_text(strip=True) if author_col else cols[8].get_text(strip=True)
        if username == author_val and str(problem_id) == problem_val:
            return {
                'runid': runid,
                'problem': problem_val,
                'result': judge_status,
                'memory': cols[5].get_text(strip=True),
                'time': cols[4].get_text(strip=True),
                'language': cols[7].get_text(strip=True),
                'raw_html': str(r)
            }
    return None

# --- fetch_compile_info improved to detect "No such error message" ---

def fetch_compile_info(session, runid, headers):
    urls = [
        f"{HDU_BASE}/showerror.php?solution_id={runid}",
        f"{HDU_BASE}/showcompileinfo.php?rid={runid}",
        f"{HDU_BASE}/viewerror.php?rid={runid}",
    ]
    for url in urls:
        try:
            r = session.get(url, headers=headers, timeout=8)
            if r.status_code==200:
                r.encoding = 'gb2312'
                soup = BeautifulSoup(r.text, 'html.parser')
                pre_tags = soup.find_all('pre')
                if pre_tags:
                    text = '\n'.join(pre.get_text() for pre in pre_tags).strip()
                    if text and 'No such error message' not in text:
                        return text
        except: pass
    return ''

if __name__=='__main__':
    app.run(debug=True)
