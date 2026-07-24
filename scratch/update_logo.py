import os
import re

with open('static/cau_logo_base64.txt', 'r', encoding='utf-8') as f:
    b64_orig = f.read().strip()

# 1. Update templates/base.html
base_path = 'templates/base.html'
with open(base_path, 'r', encoding='utf-8') as f:
    bcontent = f.read()

new_cau_wrap_base = '''      <div class="cau-logo-wrap">
        <div style="background:#ffffff;padding:4px 10px;border-radius:6px;display:inline-flex;align-items:center;margin-top:4px;box-shadow:0 2px 6px rgba(0,0,0,0.18);">
          <img src="{{ url_for('static', filename='cau_logo.png') }}" alt="중앙대학교병원" style="height:26px;width:auto;display:block;">
        </div>
      </div>'''

new_collapsed_icon_base = '''    <div class="header-collapsed-icon">
      <div style="background:#ffffff;padding:4px;border-radius:6px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,0.18);">
        <img src="{{ url_for('static', filename='cau_logo.png') }}" alt="중앙대학교병원" style="height:24px;width:24px;object-fit:cover;object-position:left;">
      </div>
    </div>'''

bcontent = re.sub(r'<div class="cau-logo-wrap">.*?</div>\s*</div>', new_cau_wrap_base + '\n    </div>', bcontent, flags=re.DOTALL)
bcontent = re.sub(r'<div class="header-collapsed-icon">.*?</div>', new_collapsed_icon_base, bcontent, flags=re.DOTALL)

with open(base_path, 'w', encoding='utf-8') as f:
    f.write(bcontent)
print('Successfully updated base.html')

# 2. Update worklog.html
worklog_path = 'worklog.html'
with open(worklog_path, 'r', encoding='utf-8') as f:
    wcontent = f.read()

new_cau_wrap_worklog = f'''          <div class="cau-logo-wrap">
            <div style="background:#ffffff;padding:4px 10px;border-radius:6px;display:inline-flex;align-items:center;margin-top:4px;box-shadow:0 2px 6px rgba(0,0,0,0.18);">
              <img src="{b64_orig}" alt="중앙대학교병원" style="height:26px;width:auto;display:block;">
            </div>
          </div>'''

new_collapsed_icon_worklog = f'''        <div class="header-collapsed-icon">
          <div style="background:#ffffff;padding:4px;border-radius:6px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,0.18);">
            <img src="{b64_orig}" alt="중앙대학교병원" style="height:24px;width:24px;object-fit:cover;object-position:left;">
          </div>
        </div>'''

wcontent = re.sub(r'<div class="cau-logo-wrap">.*?</div>\s*</div>\s*<div class="header-collapsed-icon">.*?</div>', new_cau_wrap_worklog + '\n        </div>\n' + new_collapsed_icon_worklog, wcontent, flags=re.DOTALL)

login_logo_worklog = f'''      <div class="logo">
        <div style="font-size:13px;color:#556b82;font-weight:500;margin-bottom:2px;text-align:center;">중앙대학교 병원</div>
        <h1 style="font-size:19px;font-weight:700;color:#1e2a3a;margin-bottom:14px;text-align:center;">영상의학과 업무일지</h1>
        <div style="display:flex;justify-content:center;margin-bottom:6px;">
          <img src="{b64_orig}" alt="중앙대학교병원" style="height:38px;width:auto;">
        </div>
      </div>'''

wcontent = re.sub(r'<div class="logo">.*?</div>\s*<div id="login-alert"', login_logo_worklog + '\n      <div id="login-alert"', wcontent, flags=re.DOTALL)

with open(worklog_path, 'w', encoding='utf-8') as f:
    f.write(wcontent)
print('Successfully updated worklog.html')

# 3. Update templates/login.html
login_path = 'templates/login.html'
with open(login_path, 'r', encoding='utf-8') as f:
    lcontent = f.read()

new_login_logo = '''  <div class="logo">
    <div style="font-size:13px;color:#556b82;font-weight:500;margin-bottom:2px;text-align:center;">중앙대학교 병원</div>
    <h1 style="font-size:19px;font-weight:700;color:#1e2a3a;margin-bottom:14px;text-align:center;">영상의학과 업무일지</h1>
    <div style="display:flex;justify-content:center;margin-bottom:6px;">
      <img src="{{ url_for('static', filename='cau_logo.png') }}" alt="중앙대학교병원" style="height:38px;width:auto;">
    </div>
  </div>'''

lcontent = re.sub(r'<div class="logo">.*?</div>', new_login_logo, lcontent, flags=re.DOTALL)

with open(login_path, 'w', encoding='utf-8') as f:
    f.write(lcontent)
print('Successfully updated login.html')
