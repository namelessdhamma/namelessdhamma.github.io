"""Native AF-Next private GPU audio-input test; public synthetic sounds only."""
import hashlib
import json
import math
import pathlib
import subprocess
import sys
import time
import wave

ROOT = pathlib.Path('/kaggle/working')
OUT = ROOT / 'true-sound-afnext-full-r1'
OUT.mkdir(exist_ok=False)
REV = '5634886e2615c2f587dcf8b93c6edfe9907930ca'
MODEL_SHA = 'abe72a07b5c22faaefc0a611b57f4c81e3439d095dd01738f23fb9da054f39c3'
PROMPT = ('Describe the audible sounds, their texture, and how often they occur. '
          'Give approximate start and end times for discrete events. '
          'State whether there is speech or singing; if unclear, say unclear.')


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''): h.update(block)
    return h.hexdigest()


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2))
    print(name, json.dumps(obj), flush=True)


def main():
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet',
                    'transformers==5.19.0', 'accelerate', 'soundfile', 'librosa'], check=True, timeout=300)
    import numpy as np
    import torch
    import soundfile as sf
    from huggingface_hub import snapshot_download
    from transformers import AutoProcessor, MusicFlamingoForConditionalGeneration
    assert torch.cuda.is_available(), 'GPU_NOT_AVAILABLE_NO_CPU_FALLBACK'
    model_dir = pathlib.Path(snapshot_download('nvidia/audio-flamingo-next-hf', revision=REV,
        allow_patterns=['model.safetensors', '*.json', '*.jinja', 'LICENSE']))
    assert sha(model_dir / 'model.safetensors') == MODEL_SHA
    processor = AutoProcessor.from_pretrained(model_dir)
    started = time.time()
    capacities = {i:'13GiB' for i in range(torch.cuda.device_count())}
    capacities['cpu'] = '16GiB'
    model = MusicFlamingoForConditionalGeneration.from_pretrained(
        model_dir, dtype=torch.float16, device_map='auto', max_memory=capacities,
        attn_implementation='sdpa').eval()
    assert not getattr(model, 'is_quantized', False)
    write('model-ready.json', {'revision':REV, 'dtype':str(model.dtype), 'quantized':False,
        'device_map':{k:str(v) for k,v in model.hf_device_map.items()},
        'gpus':[{'name':torch.cuda.get_device_name(i),
                 'total_bytes':torch.cuda.get_device_properties(i).total_memory}
                for i in range(torch.cuda.device_count())],
        'loading_seconds':time.time()-started,'model_sha256':MODEL_SHA,
        'native_gpt_hearing':False, 'private_audio_uploaded':False})
    rate = 16000
    count = 6*rate
    # The fixtures are public and generated independently of expected model answers.
    rng = np.random.default_rng(20261013)
    noise = np.zeros(count, dtype=np.float32)
    noise[int(.5*rate):int(5.5*rate)] = rng.normal(0,.11,5*rate)
    chirps = np.zeros(count, dtype=np.float32)
    for start in [.6,2.6,4.6]:
        t = np.arange(int(.5*rate))/rate
        tone = .35*np.sin(2*np.pi*(500*t+600*t*t))
        tone *= np.sin(np.pi*np.arange(len(t))/len(t))**2
        chirps[int(start*rate):int(start*rate)+len(t)] = tone
    for sid, audio in [('a', chirps), ('b', noise)]:
        wav = OUT / (sid + '.wav')
        sf.write(wav, audio, rate, subtype='PCM_16')
        y, raw_rate = sf.read(wav, dtype='float32')
        conversation = [[{'role':'user','content':[{'type':'text','text':PROMPT},
                        {'type':'audio','path':str(wav)}]}]]
        inputs = processor.apply_chat_template(conversation, tokenize=True,
            add_generation_prompt=True, return_dict=True, return_tensors='pt').to(model.device)
        inputs['input_features'] = inputs['input_features'].to(model.dtype)
        begin = time.time()
        with torch.inference_mode():
            output = model.generate(**inputs, do_sample=False, max_new_tokens=256, repetition_penalty=1.2,
                eos_token_id=processor.tokenizer.eos_token_id,
                pad_token_id=processor.tokenizer.pad_token_id)
        ids = output[0, inputs['input_ids'].shape[1]:].tolist()
        answer = processor.batch_decode(output[:,inputs['input_ids'].shape[1]:],
            skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        write(sid+'-receipt.json', {'sample_id':sid, 'input_sha256':sha(wav),
            'model_input_samples':len(y),'model_input_rate':raw_rate,
            'input_feature_shape':list(inputs['input_features'].shape),
            'answer':answer,'prompt':PROMPT,'generated_ids':ids,
            'eos_id':processor.tokenizer.eos_token_id, 'seconds':time.time()-begin,
            'actual_model_input':True,'qualification':'UNADJUDICATED_PUBLIC_SYNTHETIC_OBSERVATION'})
    frozen = {f.name:sha(f) for f in OUT.iterdir() if f.is_file()}
    write('frozen-results.json', frozen)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        write('failure.json', {'type':type(error).__name__,'message':str(error)[:1000],
                              'qualification':'NO_AUDIO_INPUT_QUALIFICATION'})
        raise

