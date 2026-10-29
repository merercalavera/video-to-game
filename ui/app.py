#!/usr/bin/env python3
"""A small local UI around the video-to-game scripts.

It prepares a project folder (projects/<name>/) with the gameplay video and its prompt, studies the video, gives
you the request to paste into your coding agent (which builds the game), and serves the finished game.

Usage:
  .venv\\Scripts\\python.exe ui/app.py        (Windows)
  .venv/bin/python ui/app.py                (macOS, Linux)

Needs `pip install -r ui/requirements.txt`, ffmpeg on PATH, and FAL_KEY in .env to generate videos.
"""
import os
import re
import shutil
import subprocess
import sys

import gradio as gr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'skills', 'video-to-game', 'scripts')
PROJECTS = os.path.join(ROOT, 'projects')
VIDEO_MODEL = 'minimax/h3-max/text-to-video'
PORT = 8000
server = None


def slug(name):
    s = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
    if not s:
        raise gr.Error('Give the project a name first.')
    return s


def project_dir(name):
    d = os.path.join(PROJECTS, slug(name))
    os.makedirs(d, exist_ok=True)
    return d


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, '/')


def fal_key_status():
    path = os.path.join(ROOT, '.env')
    has = os.environ.get('FAL_KEY') or (os.path.exists(path) and re.search(
        r'^\s*FAL_KEY\s*=\s*\S', open(path, encoding='utf-8').read(), re.M))
    return 'FAL_KEY found.' if has else '**FAL_KEY missing:** add it to `.env` at the repo root to generate videos.'


def save_prompt(d, prompt):
    if prompt and prompt.strip():
        with open(os.path.join(d, 'gameplay.txt'), 'w', encoding='utf-8') as f:
            f.write(prompt.strip() + '\n')


def use_upload(name, video, prompt):
    if not video:
        raise gr.Error('Upload a video first.')
    d = project_dir(name)
    dest = os.path.join(d, 'gameplay.mp4')
    shutil.copyfile(video, dest)
    save_prompt(d, prompt)
    return dest, f'Saved `{rel(dest)}`.'


def generate(name, prompt, duration):
    if not prompt or not prompt.strip():
        raise gr.Error('Write a gameplay prompt first.')
    d = project_dir(name)
    save_prompt(d, prompt)
    cmd = [sys.executable, os.path.join(SCRIPTS, 'fal_asset.py'), VIDEO_MODEL, '-o', d, '--name', 'gameplay',
           '--arg', f'prompt={prompt.strip()}', '--arg', f'duration={int(duration)}', '--arg', 'resolution=1080P',
           '--arg', 'aspect_ratio=16:9', '--arg', 'prompt_expansion_mode=disabled']
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    dest = os.path.join(d, 'gameplay.mp4')
    if r.returncode or not os.path.exists(dest):
        raise gr.Error(f'Generation failed:\n{(r.stderr or r.stdout)[-1500:]}')
    return dest, f'Generated `{rel(dest)}` with `{VIDEO_MODEL}` (logged in `{rel(d)}/fal_log.json`).'


def study(name):
    d = project_dir(name)
    video = os.path.join(d, 'gameplay.mp4')
    if not os.path.exists(video):
        raise gr.Error('No gameplay.mp4 in this project yet.')
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'study_video.py'), video, '-o',
                        os.path.join(d, 'study')], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        raise gr.Error(f'Study failed:\n{r.stderr[-1500:]}')
    return os.path.join(d, 'study', 'sheet.jpg'), r.stdout.strip()


def agent_request(name):
    d = project_dir(name)
    p = rel(d)
    prompt_line = (f' The prompt that made it is in `{p}/gameplay.txt`.'
                   if os.path.exists(os.path.join(d, 'gameplay.txt')) else '')
    return (f'Turn `{p}/gameplay.mp4` into a playable browser game with the video-to-game skill.{prompt_line} '
            f'The study (frames, contact sheet, palette) is in `{p}/study/`. Put the game in `{p}/game/` '
            f'(index.html + assets/). Generate every asset with fal using the venv Python '
            f'(`.venv/Scripts/python.exe`), match the video\'s look, and show me side-by-side pairs and a recorded '
            f'take of you playing it. Tell me the fal cost before and after.')


def serve(name):
    global server
    game = os.path.join(project_dir(name), 'game')
    if not os.path.exists(os.path.join(game, 'index.html')):
        raise gr.Error(f'No {rel(game)}/index.html yet: the agent builds it.')
    if server and server.poll() is None:
        server.terminate()
    server = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT), '--bind', '127.0.0.1'], cwd=game)
    url = f'http://127.0.0.1:{PORT}/'
    return f'Serving `{rel(game)}` at [{url}]({url}) (or [{url}?autostart]({url}?autostart)).'


with gr.Blocks(title='Video to Game') as app:
    gr.Markdown('# Video to Game\nPrepare a project, then let your coding agent build the game from it.')
    key = gr.Markdown(fal_key_status())
    name = gr.Textbox(label='Project name', placeholder='e.g. lantern-keeper')

    with gr.Tab('1. Video'):
        prompt = gr.Textbox(label='Gameplay prompt (one original concept, one visible mechanic, no HUD)', lines=4,
                            placeholder='A girl carrying a small glowing ember walks through a charcoal-drawn burnt '
                                        'forest; the ember redraws the trees in color as she passes.')
        with gr.Row():
            with gr.Column():
                gr.Markdown(f'**Generate** with `{VIDEO_MODEL}` (paid, takes a few minutes).')
                duration = gr.Radio([10, 15], value=10, label='Seconds')
                gen_btn = gr.Button('Generate video', variant='primary')
            with gr.Column():
                gr.Markdown('**Or upload** a clip you already have (10 to 15 s, 16:9).')
                upload = gr.File(label='Video file', file_types=['video'], type='filepath')
                up_btn = gr.Button('Use this video')
        video = gr.Video(label='Project video', interactive=False)
        video_status = gr.Markdown()

    with gr.Tab('2. Study'):
        study_btn = gr.Button('Study the video (frames, contact sheet, palette, cuts)', variant='primary')
        study_out = gr.Textbox(label='Summary', lines=2)
        sheet = gr.Image(label='Contact sheet', type='filepath')

    with gr.Tab('3. Build with the agent'):
        gr.Markdown('Paste this into Claude Code (or another agent with the skill). The agent writes the game, '
                    'generates the assets with fal and playtests it.')
        req_btn = gr.Button('Write the request')
        request = gr.Code(label='Request', language='markdown', interactive=False)

    with gr.Tab('4. Play'):
        play_btn = gr.Button('Serve the game', variant='primary')
        play_status = gr.Markdown()

    gen_btn.click(generate, [name, prompt, duration], [video, video_status])
    up_btn.click(use_upload, [name, upload, prompt], [video, video_status])
    study_btn.click(study, [name], [sheet, study_out])
    req_btn.click(agent_request, [name], [request])
    play_btn.click(serve, [name], [play_status])
    app.load(fal_key_status, None, key)

if __name__ == '__main__':
    app.launch(allowed_paths=[PROJECTS])
