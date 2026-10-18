import os
import sys
import wave
import subprocess
import win32com.client

SEGMENTS = [
    {
        "id": "seg1_intro",
        "start_sec": 1.5,
        "text": "Welcome to the Pharos Saga Executor demonstration. In decentralized applications, multi-step workflows often fail midway, leaving user assets stranded. Saga Executor solves this by coordinating deterministic multi-step transactions on Pharos Atlantic Testnet with zero simulation and built-in compensation."
    },
    {
        "id": "seg2_connect",
        "start_sec": 23.0,
        "text": "The user connects a live browser wallet. The interface reads on-chain balances directly from Atlantic Testnet RPC: over twenty-eight thousand native Pharos and 1.75 wrapped Pharos. No simulated balances or mock state are ever used."
    },
    {
        "id": "seg3_wrap_prompt",
        "start_sec": 42.5,
        "text": "We initiate our forward workflow: wrapping 0.0001 native Pharos. MetaMask prompts for explicit wallet authorization. Every state change requires explicit user approval. Once signed, the transaction is broadcast to the network, and the executor awaits verified receipt confirmation."
    },
    {
        "id": "seg4_wrap_mined",
        "start_sec": 68.0,
        "text": "Block 31,579,889 mines the wrap transaction, consuming twenty-eight thousand gas. The executor inspects the receipt status and verifies the updated balance before advancing the workflow."
    },
    {
        "id": "seg5_unwrap_prompt",
        "start_sec": 86.0,
        "text": "Next, we demonstrate the compensation pathway by triggering an unwrap withdrawal. Saga Executor invokes the verified withdraw method on the wrapped Pharos contract. MetaMask requests the second user signature to authorize the unwinding."
    },
    {
        "id": "seg6_unwrap_mined",
        "start_sec": 112.0,
        "text": "The unwrap confirms in block 31,579,910, using thirty-five thousand gas. The executor verifies receipt status one, confirming our native Pharos principal has been safely restored."
    },
    {
        "id": "seg7_summary",
        "start_sec": 127.0,
        "text": "Pharos Saga Executor delivers reliable, auditable decentralized transaction execution. Every step is verifiable on Pharoscan, with explicit wallet approvals and guaranteed state recovery."
    }
]

def synthesize_segments(output_dir, voice_name="Microsoft David Desktop"):
    os.makedirs(output_dir, exist_ok=True)
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    
    # Select voice
    voices = speaker.GetVoices()
    selected_voice = None
    for v in voices:
        if voice_name.lower() in v.GetDescription().lower():
            selected_voice = v
            break
    if selected_voice:
        speaker.Voice = selected_voice
    
    # Rate: 0 is default normal speed (-10 to 10)
    speaker.Rate = 0
    speaker.Volume = 100
    
    generated = []
    
    for seg in SEGMENTS:
        wav_path = os.path.join(output_dir, f"{seg['id']}.wav")
        file_stream = win32com.client.Dispatch("SAPI.SpFileStream")
        # 39 = SAFT48kHz16BitStereo, 35 = SAFT44kHz16BitStereo, 22 = SAFT22kHz16BitStereo
        file_stream.Format.Type = 39 
        file_stream.Open(wav_path, 3, False) # 3 = SSFMCreateForWrite
        
        speaker.AudioOutputStream = file_stream
        speaker.Speak(seg["text"])
        file_stream.Close()
        
        # Read duration
        with wave.open(wav_path, 'r') as w:
            frames = w.getnframes()
            rate = w.getframerate()
            duration = frames / float(rate)
            
        seg_info = dict(seg)
        seg_info["file"] = wav_path
        seg_info["duration"] = round(duration, 2)
        seg_info["end_sec"] = round(seg["start_sec"] + duration, 2)
        generated.append(seg_info)
        print(f"[{seg['id']}] start: {seg['start_sec']}s, dur: {duration:.2f}s, end: {seg_info['end_sec']}s")
        
    return generated

if __name__ == "__main__":
    out_dir = os.path.join("demo-output", "segments")
    gen = synthesize_segments(out_dir)
    print("\nTotal segments generated:", len(gen))
