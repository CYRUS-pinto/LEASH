import asyncio
import os
import edge_tts
import json
import subprocess

SCENES = [
    {
        "id": 1,
        "name": "Hook",
        "target_start": 0.0,
        "target_duration": 3.0,
        "text": "One poisoned support ticket. That is all it takes to turn an enterprise's own autonomous AI agent into an insider threat."
    },
    {
        "id": 2,
        "name": "Blast Radius",
        "target_start": 3.0,
        "target_duration": 8.0,
        "text": "By 2028, a third of enterprise software will run on autonomous agents holding live credentials to databases and payment rails. In India, where an average data breach costs 25.5 crore rupees, sixty-three percent of firms still lack AI access controls."
    },
    {
        "id": 3,
        "name": "Thesis",
        "target_start": 11.0,
        "target_duration": 8.0,
        "text": "Today's observability tools only log what agents say—after the money moves or customer data leaves. Logs are a rear-view mirror. LEASH is the brake."
    },
    {
        "id": 4,
        "name": "Architecture",
        "target_start": 19.0,
        "target_duration": 13.0,
        "text": "Meet LEASH: the deterministic action-control gateway built on Python 3.13 and FastAPI. Every action an agent proposes passes through eight policy-as-code stages—verifying not just intent, but the actual effect against the System of Record."
    },
    {
        "id": 5,
        "name": "Live Attack Demo",
        "target_start": 32.0,
        "target_duration": 23.0,
        "text": "Watch a live attack. A naive support agent reads a poisoned ticket and proposes exfiltrating customer PII via email. Before that request ever touches the mail server, LEASH flags the untrusted recipient taint and PII in the body—blocking the action, quarantining the agent, and writing a tamper-evident SHA-256 receipt in 7.9 milliseconds."
    },
    {
        "id": 6,
        "name": "Golden Ratio Climax",
        "target_start": 55.0,
        "target_duration": 21.0,
        "text": "Why do effect checks matter? On the LaunderBench-mini benchmark, taint-only defenses were bypassed by one hundred percent of paraphrased and Hindi or Kannada translated attacks. By verifying parameters against the System of Record, LEASH stopped all forty-eight attacks—with zero false blocks on benign actions and a median latency of 7.9 milliseconds."
    },
    {
        "id": 7,
        "name": "Resolution & CTA",
        "target_start": 76.0,
        "target_duration": 13.0,
        "text": "With one-click human escalation and DPDP-ready hash-chained audits, enterprises can finally deploy autonomous agents where they pay. Priced like software. Saves like insurance. Put autonomous agents on a LEASH."
    }
]

async def synthesize_all():
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "audio"))
    os.makedirs(out_dir, exist_ok=True)
    voice = "en-US-AndrewNeural"
    rate = "+3%"

    timeline_data = []

    print(f"Synthesizing {len(SCENES)} scenes with voice={voice}, rate={rate}...")
    for s in SCENES:
        mp3_path = os.path.join(out_dir, f"scene_{s['id']:02d}.mp3")
        srt_path = os.path.join(out_dir, f"scene_{s['id']:02d}.vtt")
        
        communicate = edge_tts.Communicate(s["text"], voice=voice, rate=rate)
        submaker = edge_tts.SubMaker()
        
        with open(mp3_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)
                    
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(submaker.get_srt())
            
        # Probe exact duration
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', mp3_path]
        res = subprocess.check_output(cmd)
        dur = float(json.loads(res)['format']['duration'])
        
        print(f"Scene {s['id']} ({s['name']}): duration={dur:.2f}s (budget: {s['target_duration']}s)")
        
        timeline_data.append({
            "id": s["id"],
            "name": s["name"],
            "target_start": s["target_start"],
            "target_duration": s["target_duration"],
            "actual_duration": dur,
            "text": s["text"],
            "mp3_file": f"scene_{s['id']:02d}.mp3"
        })

    json_path = os.path.join(out_dir, "narration_timeline.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(timeline_data, f, indent=2)
    print(f"Wrote narration timeline to {json_path}")

if __name__ == "__main__":
    asyncio.run(synthesize_all())
