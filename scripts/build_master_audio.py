import os
import sys
import wave
import struct
import subprocess
import win32com.client

SEGMENTS = [
    {
        "id": "seg1_intro",
        "scene": "Project & Architecture Introduction",
        "start_sec": 1.5,
        "text": "Welcome to the Pharos Saga Executor demonstration. In decentralized applications, multi-step workflows often fail midway, leaving user assets stranded. Saga Executor solves this by coordinating deterministic multi-step transactions on Pharos Atlantic Testnet with zero simulation and built-in compensation."
    },
    {
        "id": "seg2_connect",
        "scene": "Wallet Connection & On-Chain State Discovery",
        "start_sec": 23.5,
        "text": "The user connects a live browser wallet. The interface reads on-chain balances directly from Atlantic Testnet RPC: over twenty-eight thousand native Pharos and 1.75 wrapped Pharos. No simulated balances or mock state are ever used."
    },
    {
        "id": "seg3_wrap_prompt",
        "scene": "Action 1: Forward Wrap Deposit Initiation",
        "start_sec": 42.5,
        "text": "We initiate our forward workflow: wrapping 0.0001 native Pharos. MetaMask prompts for explicit wallet authorization. Every state change requires explicit user approval. Once signed, the transaction is broadcast to the network, and the executor awaits verified receipt confirmation."
    },
    {
        "id": "seg4_wrap_mined",
        "scene": "Action 1: Wrap Confirmation & Receipt Barrier",
        "start_sec": 68.0,
        "text": "Block 31,579,889 mines the wrap transaction, consuming twenty-eight thousand gas. The executor inspects the receipt status and verifies the updated balance before advancing the workflow."
    },
    {
        "id": "seg5_unwrap_prompt",
        "scene": "Action 2: Reverse LIFO Compensation Initiation",
        "start_sec": 86.0,
        "text": "Next, we demonstrate the compensation pathway by triggering an unwrap withdrawal. Saga Executor invokes the verified withdraw method on the wrapped Pharos contract. MetaMask requests the second user signature to authorize the unwinding."
    },
    {
        "id": "seg6_unwrap_mined",
        "scene": "Action 2: Unwrap Confirmation & Principal Restored",
        "start_sec": 108.0,
        "text": "The unwrap confirms in block 31,579,910, consuming thirty-five thousand gas. Verified receipt status one confirms our native Pharos principal has been safely restored."
    },
    {
        "id": "seg7_summary",
        "scene": "Audit Trail & Production Guarantees",
        "start_sec": 126.0,
        "text": "Pharos Saga Executor delivers reliable, auditable decentralized workflows. Every step is verifiable on Pharoscan, with explicit wallet approvals and guaranteed state recovery."
    }
]

def synthesize_and_build_master():
    seg_dir = os.path.join("demo-output", "segments")
    os.makedirs(seg_dir, exist_ok=True)
    
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    for v in speaker.GetVoices():
        if "david" in v.GetDescription().lower():
            speaker.Voice = v
            break
            
    speaker.Rate = 0
    speaker.Volume = 100
    
    total_duration_sec = 141.55
    sample_rate = 48000
    channels = 2
    sample_width = 2 # 16-bit
    total_frames = int(total_duration_sec * sample_rate)
    
    # Master audio buffer: initialize with zeros (silence)
    # 2 channels * 2 bytes = 4 bytes per frame
    master_frames = bytearray(total_frames * channels * sample_width)
    
    print(f"Master audio buffer created: {total_frames} frames ({total_duration_sec}s)")
    
    metadata = []
    
    for seg in SEGMENTS:
        wav_path = os.path.join(seg_dir, f"{seg['id']}.wav")
        fs = win32com.client.Dispatch("SAPI.SpFileStream")
        fs.Format.Type = 39 # SAFT48kHz16BitStereo
        fs.Open(wav_path, 3, False)
        speaker.AudioOutputStream = fs
        speaker.Speak(seg["text"])
        fs.Close()
        
        with wave.open(wav_path, 'r') as w:
            n_frames = w.getnframes()
            w_rate = w.getframerate()
            w_channels = w.getnchannels()
            w_width = w.getsampwidth()
            audio_bytes = w.readframes(n_frames)
            
        dur = n_frames / float(w_rate)
        start_frame = int(seg["start_sec"] * sample_rate)
        byte_offset = start_frame * channels * sample_width
        
        # Splice audio_bytes into master_frames
        end_byte = byte_offset + len(audio_bytes)
        if end_byte > len(master_frames):
            copy_len = len(master_frames) - byte_offset
            master_frames[byte_offset:byte_offset + copy_len] = audio_bytes[:copy_len]
        else:
            master_frames[byte_offset:end_byte] = audio_bytes
            
        seg_meta = dict(seg)
        seg_meta["duration_sec"] = round(dur, 2)
        seg_meta["end_sec"] = round(seg["start_sec"] + dur, 2)
        metadata.append(seg_meta)
        print(f"Placed {seg['id']} at {seg['start_sec']}s - {seg_meta['end_sec']}s (dur: {dur:.2f}s)")
        
    master_wav_path = os.path.join("demo-output", "narration_master.wav")
    with wave.open(master_wav_path, 'w') as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(master_frames)
        
    print(f"Saved master narration to {master_wav_path}")
    return metadata

if __name__ == "__main__":
    meta = synthesize_and_build_master()
