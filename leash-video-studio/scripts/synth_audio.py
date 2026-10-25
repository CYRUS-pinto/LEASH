import numpy as np
import scipy.signal as signal
import soundfile as sf
import os
import json
import subprocess

SAMPLE_RATE = 48000

def create_sub_bass_drop(duration=0.85):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    # Frequency sweep 110Hz down to 42Hz
    freq = np.geomspace(110, 42, len(t))
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    # Envelope
    env = np.exp(-3.5 * t)
    # Add saturation harmonic
    wave = np.sin(phase) + 0.3 * np.sin(2 * phase)
    wave = np.tanh(1.5 * wave) * env
    return wave

def create_metallic_latch(duration=0.15):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    # Click transient + high metallic ping
    noise = np.random.uniform(-1, 1, len(t)) * np.exp(-45 * t)
    ping = np.sin(2 * np.pi * 3200 * t) * np.exp(-30 * t) + np.sin(2 * np.pi * 4800 * t) * np.exp(-40 * t)
    return (0.6 * noise + 0.4 * ping)

def create_keystroke(duration=0.08):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    noise = np.random.uniform(-1, 1, len(t)) * np.exp(-60 * t)
    thump = np.sin(2 * np.pi * 180 * t) * np.exp(-40 * t)
    return 0.4 * noise + 0.6 * thump

def create_cloth_whoosh(duration=0.45):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    noise = np.random.uniform(-1, 1, len(t))
    # Bandpass filter around 800Hz - 2400Hz
    sos = signal.butter(4, [600 / (SAMPLE_RATE/2), 2200 / (SAMPLE_RATE/2)], btype='bandpass', output='sos')
    filtered = signal.sosfilt(sos, noise)
    # Swell envelope
    env = np.sin(np.pi * (t / duration)) ** 2
    return filtered * env * 0.7

def create_crystal_tick(freq=1046.5, duration=0.25):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    ping = np.sin(2 * np.pi * freq * t) * np.exp(-18 * t)
    harmonic = np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-25 * t) * 0.25
    return (ping + harmonic) * 0.5

def create_piano_chord(freqs, duration=3.5):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    chord = np.zeros_like(t)
    for f in freqs:
        # Piano string physics: fundamental + overtones with individual decay
        string = np.sin(2 * np.pi * f * t) * np.exp(-1.2 * t)
        string += 0.4 * np.sin(2 * np.pi * (f * 2.0) * t) * np.exp(-2.0 * t)
        string += 0.2 * np.sin(2 * np.pi * (f * 3.0) * t) * np.exp(-3.2 * t)
        string += 0.08 * np.sin(2 * np.pi * (f * 4.0) * t) * np.exp(-4.5 * t)
        chord += string
    # Normalize
    chord = chord / len(freqs)
    # Gentle hammer transient
    hammer = np.random.uniform(-1, 1, len(t)) * np.exp(-80 * t) * 0.05
    return chord + hammer

def generate_cinematic_soundtrack(total_duration=89.0):
    num_samples = int(SAMPLE_RATE * total_duration)
    t = np.linspace(0, total_duration, num_samples, False)
    
    # 1. Analog Sub-Bass Drone Stem (55Hz + 110Hz subtle harmonic)
    drone = 0.6 * np.sin(2 * np.pi * 55 * t) + 0.25 * np.sin(2 * np.pi * 110 * t)
    # Warm lowpass filter at 220Hz
    sos_drone = signal.butter(4, 220 / (SAMPLE_RATE / 2), btype='lowpass', output='sos')
    drone = signal.sosfilt(sos_drone, drone)
    
    # Volume envelope for drone:
    # Swell in 0 to 2s
    # MUTE at 00:16.2 to 00:18.8 (Dead silence right before "LEASH is the brake")
    # Swell back in at 00:19.0 through 00:86.0, then fade out
    drone_env = np.ones_like(t) * 0.15
    # Fade in
    drone_env[:int(SAMPLE_RATE * 2.0)] = np.linspace(0, 0.15, int(SAMPLE_RATE * 2.0))
    # Mute window (16.2s to 18.8s)
    idx_mute_start = int(SAMPLE_RATE * 16.2)
    idx_mute_end = int(SAMPLE_RATE * 18.8)
    drone_env[idx_mute_start:idx_mute_end] = 0.0
    # Fade out last 3 seconds
    drone_env[int(SAMPLE_RATE * 86.0):] = np.linspace(0.15, 0.0, num_samples - int(SAMPLE_RATE * 86.0))
    drone = drone * drone_env

    # 2. Warm Anthropic Acoustic Piano Stem (Chords at key narrative points)
    piano_stem = np.zeros(num_samples)
    
    # Chord progressions (Frequencies in Hz):
    # Intro: A minor (A2, C3, E3, A3)
    # Hook: F major 7 (F2, C3, E3, A3)
    # Post-Brake (19s): D minor 9 (D2, A2, C3, E3, F3)
    # LaunderBench Climax (55s): C major (C2, G2, C3, E3, G3)
    # Outro (76s): F add 9 (F2, C3, G3, A3) -> C major resolution
    chords_schedule = [
        (0.5, [110.0, 130.81, 164.81, 220.0]),      # Am
        (6.0, [87.31, 130.81, 164.81, 220.0]),      # Fmaj7
        (19.2, [73.42, 110.0, 130.81, 164.81, 174.61]), # Dm9
        (33.0, [98.00, 146.83, 174.61, 220.0]),     # G
        (55.0, [65.41, 98.00, 130.81, 164.81, 196.0]),  # Cmaj (Golden Climax)
        (76.5, [87.31, 130.81, 196.00, 220.0]),     # Fadd9
        (82.0, [65.41, 98.00, 130.81, 164.81])       # C resolve
    ]
    
    for start_t, freqs in chords_schedule:
        c = create_piano_chord(freqs, duration=5.0)
        idx_s = int(SAMPLE_RATE * start_t)
        idx_e = min(num_samples, idx_s + len(c))
        piano_stem[idx_s:idx_e] += c[:idx_e - idx_s] * 0.35

    # 3. Foley & Transient Stem
    foley_stem = np.zeros(num_samples)

    def add_sfx(sfx_wave, at_time, gain=1.0):
        idx_s = int(SAMPLE_RATE * at_time)
        idx_e = min(num_samples, idx_s + len(sfx_wave))
        foley_stem[idx_s:idx_e] += sfx_wave[:idx_e - idx_s] * gain

    # Scene 1: Pattern Interrupt Hook (00:00 - 00:03)
    add_sfx(create_keystroke(), 0.4, 0.4)
    add_sfx(create_keystroke(), 0.7, 0.4)
    add_sfx(create_sub_bass_drop(0.6), 1.5, 0.7)

    # Scene 2: Card reveals (cloth whoosh)
    add_sfx(create_cloth_whoosh(0.4), 3.2, 0.5)
    add_sfx(create_cloth_whoosh(0.4), 7.0, 0.5)

    # Scene 3: The Brake Slam at 00:18.0!
    # Precision metallic latch + sub-bass brake drop
    add_sfx(create_metallic_latch(0.18), 18.0, 0.9)
    add_sfx(create_sub_bass_drop(1.0), 18.02, 1.2)

    # Scene 4: 8 ascending crystalline ticks for Stages 0-7 (00:19.5 to 00:22.5)
    scale = [523.25, 587.33, 659.25, 783.99, 880.00, 1046.50, 1174.66, 1318.51]
    for i, freq in enumerate(scale):
        tick_t = 19.5 + i * 0.28
        add_sfx(create_crystal_tick(freq, 0.2), tick_t, 0.45)

    # Scene 5: Live Interception Alert (32s - 55s)
    for k in [32.5, 32.7, 33.0, 33.3]:
        add_sfx(create_keystroke(), k, 0.3)
    add_sfx(create_crystal_tick(1567.98, 0.3), 36.5, 0.6) # POST alert ping
    add_sfx(create_metallic_latch(0.15), 37.0, 0.8)       # BLOCK latch
    add_sfx(create_sub_bass_drop(0.8), 37.02, 0.9)        # BLOCK thud

    # Scene 6: Golden Climax Hits (55s)
    add_sfx(create_crystal_tick(1046.5, 0.5), 55.0, 0.7)
    add_sfx(create_crystal_tick(1318.5, 0.5), 55.4, 0.7)
    add_sfx(create_crystal_tick(1567.98, 0.6), 55.8, 0.8)
    add_sfx(create_sub_bass_drop(0.9), 56.2, 0.9)

    # Scene 7: Resolution Key click + Mug (76s)
    add_sfx(create_keystroke(), 76.8, 0.4)
    add_sfx(create_keystroke(), 77.2, 0.4)
    add_sfx(create_cloth_whoosh(0.5), 82.0, 0.3)

    # Master Bed Mix (Drone + Piano + Foley)
    music_bed = drone + piano_stem
    
    # Save individual stems for flexible mixing
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "audio"))
    os.makedirs(out_dir, exist_ok=True)
    
    sf.write(os.path.join(out_dir, "stem_music_bed.wav"), music_bed, SAMPLE_RATE)
    sf.write(os.path.join(out_dir, "stem_foley.wav"), foley_stem, SAMPLE_RATE)
    
    # Master mix without speech
    master_instrumental = music_bed + foley_stem
    # Soft clip limiter
    master_instrumental = np.tanh(master_instrumental * 0.95)
    sf.write(os.path.join(out_dir, "master_instrumental_89s.wav"), master_instrumental, SAMPLE_RATE)
    
    print("Synthesized procedural stems:")
    print(" - stem_music_bed.wav")
    print(" - stem_foley.wav")
    print(" - master_instrumental_89s.wav")
    return master_instrumental

if __name__ == "__main__":
    generate_cinematic_soundtrack(89.0)
