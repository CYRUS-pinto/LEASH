import asyncio
import os
import edge_tts
import soundfile as sf
import numpy as np
import subprocess

SAMPLE_RATE = 48000

SCENES_89S = [
    {
        "id": 1,
        "name": "Hook",
        "start": 0.3,
        "text": "One poisoned support ticket. That is all it takes to turn an autonomous agent into an insider threat."
    },
    {
        "id": 2,
        "name": "Blast Radius",
        "start": 3.8,
        "text": "By 2028, a third of enterprise software will run on autonomous agents with live credentials. In India, an average breach costs 25.5 crore rupees."
    },
    {
        "id": 3,
        "name": "Thesis",
        "start": 11.5,
        "text": "Today's observability tools only log after damage occurs. Logs are a rear-view mirror. LEASH is the brake."
    },
    {
        "id": 4,
        "name": "Architecture",
        "start": 19.8,
        "text": "Meet LEASH: the deterministic action-control gateway. Every action proposed passes through eight policy stages, verifying the actual effect against the System of Record."
    },
    {
        "id": 5,
        "name": "Live Attack Demo",
        "start": 33.0,
        "text": "Watch a live attack. A support agent proposes exfiltrating customer PII. Before it touches the mail server, LEASH flags the taint, blocking the action and writing a SHA-256 receipt in 7.9 milliseconds."
    },
    {
        "id": 6,
        "name": "Golden Ratio Climax",
        "start": 55.0, # EXACT Golden Point (89 * 0.618 = 55.0s)
        "text": "Why do effect checks matter? On LaunderBench, taint defenses missed 100% of paraphrased and translated attacks. LEASH stopped all 48 attacks, with zero false blocks and a median latency of 7.9 milliseconds."
    },
    {
        "id": 7,
        "name": "Resolution & CTA",
        "start": 76.5,
        "text": "With one-click human escalation and DPDP-ready hash audits, enterprises can deploy agents safely. Priced like software. Saves like insurance. Put autonomous agents on a LEASH."
    }
]

async def build_89s_narration():
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "audio"))
    os.makedirs(out_dir, exist_ok=True)
    voice = "en-US-AndrewNeural"
    rate = "+6%" # brisk professional pacing

    num_samples = int(SAMPLE_RATE * 89.0)
    speech_track = np.zeros(num_samples)

    print("Building frame-accurate 89s narration track...")
    for s in SCENES_89S:
        tmp_mp3 = os.path.join(out_dir, f"tmp_voice_{s['id']}.mp3")
        tmp_wav = os.path.join(out_dir, f"tmp_voice_{s['id']}.wav")
        
        communicate = edge_tts.Communicate(s["text"], voice=voice, rate=rate)
        await communicate.save(tmp_mp3)
        
        # Convert to WAV 48kHz mono
        cmd = ['ffmpeg', '-y', '-i', tmp_mp3, '-ar', str(SAMPLE_RATE), '-ac', '1', tmp_wav]
        subprocess.run(cmd, check=True, capture_output=True)
        
        data, sr = sf.read(tmp_wav)
        dur = len(data) / sr
        print(f"Scene {s['id']} [{s['name']}] at {s['start']}s: duration={dur:.2f}s")
        
        idx_s = int(SAMPLE_RATE * s["start"])
        idx_e = min(num_samples, idx_s + len(data))
        speech_track[idx_s:idx_e] += data[:idx_e - idx_s]
        
        # Cleanup tmp
        if os.path.exists(tmp_mp3): os.remove(tmp_mp3)
        if os.path.exists(tmp_wav): os.remove(tmp_wav)

    # Highpass filter 80Hz and normalize speech
    sos = sf_highpass = None
    import scipy.signal as signal
    sos = signal.butter(4, 80 / (SAMPLE_RATE / 2), btype='highpass', output='sos')
    speech_track = signal.sosfilt(sos, speech_track)
    
    # Save speech stem
    speech_path = os.path.join(out_dir, "stem_speech_89s.wav")
    sf.write(speech_path, speech_track, SAMPLE_RATE)
    print(f"Saved {speech_path}")
    
    # Now mix with instrumental bed:
    inst_path = os.path.join(out_dir, "master_instrumental_89s.wav")
    inst_data, _ = sf.read(inst_path)
    
    # Sidechain ducking: wherever speech is > 0.05, duck instrumental by -10dB (0.3x)
    speech_abs = np.abs(speech_track)
    # Smooth envelope
    kernel = np.ones(int(SAMPLE_RATE * 0.15)) / int(SAMPLE_RATE * 0.15)
    env = np.convolve(speech_abs, kernel, mode='same')
    duck_gain = np.where(env > 0.02, 0.35, 1.0)
    
    # Smooth ducking transitions
    duck_gain = np.convolve(duck_gain, kernel, mode='same')
    
    mixed = (inst_data * duck_gain) + (speech_track * 1.3)
    # Limiter / soft clip
    mixed = np.tanh(mixed * 0.95)
    
    mix_path = os.path.join(out_dir, "final_master_audio_89s.wav")
    sf.write(mix_path, mixed, SAMPLE_RATE)
    
    # Convert to AAC m4a with EBU R128 loudnorm (-14 LUFS)
    m4a_path = os.path.join(out_dir, "final_master_audio_89s.m4a")
    cmd_norm = [
        'ffmpeg', '-y', '-i', mix_path,
        '-af', 'loudnorm=I=-14:TP=-1.5:LRA=7',
        '-c:a', 'aac', '-b:a', '192k',
        m4a_path
    ]
    subprocess.run(cmd_norm, check=True, capture_output=True)
    print(f"Broadcast mastered audio created at {m4a_path} (-14 LUFS compliance)")

if __name__ == "__main__":
    asyncio.run(build_89s_narration())
