"""Disposable private Kaggle audio-input test on public synthetic sounds only."""
import hashlib
import json
import math
import pathlib
import subprocess
import sys
import time
import wave

ROOT = pathlib.Path('/kaggle/working')
OUT = ROOT / 'true-sound-qwen-full-r1'
OUT.mkdir(exist_ok=False)
REV = 'f75b40e3da2003cdd6e1829b1f420ca70797c34e'
SHARDS = {'model-00001-of-00003.safetensors':
          '349972cebff443030e9e96e1e930d7230979c6961cf046fa29fc580e4bcf49a6',
          'model-00002-of-00003.safetensors':
          'b29a76dfefb3aa33a5bd0faa19c681d039a44de57223653ea0e933df728c6d8c'}
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
                    'transformers==5.19.0', 'soundfile', 'librosa'], check=True, timeout=300)
    import numpy as np
    import torch
    import soundfile as sf
    from huggingface_hub import snapshot_download
    from transformers import (Qwen2_5OmniConfig, Qwen2_5OmniProcessor,
                              Qwen2_5OmniThinkerForConditionalGeneration)
    assert torch.cuda.is_available(), 'GPU_NOT_AVAILABLE_NO_CPU_FALLBACK'
    model_dir = pathlib.Path(snapshot_download('Qwen/Qwen2.5-Omni-3B', revision=REV,
        allow_patterns=['*.json', '*.txt', '*.model', '*.tiktoken', 'LICENSE'] + list(SHARDS)))
    for name, expected in SHARDS.items(): assert sha(model_dir / name) == expected
    index_file = model_dir / 'model.safetensors.index.json'
    original_index_sha = sha(index_file)
    index = json.loads(index_file.read_text())
    index['weight_map'] = {k:v for k,v in index['weight_map'].items() if k.startswith('thinker.')}
    assert index['weight_map'] and set(index['weight_map'].values()) == set(SHARDS)
    index_file.write_text(json.dumps(index, indent=2))
    processor = Qwen2_5OmniProcessor.from_pretrained(model_dir, backend='torchvision')
    cfg = Qwen2_5OmniConfig.from_pretrained(model_dir)
    started = time.time()
    model = Qwen2_5OmniThinkerForConditionalGeneration.from_pretrained(
        model_dir, config=cfg.thinker_config, dtype=torch.float16,
        device_map={'': 'cuda:0'}, attn_implementation='sdpa')
    model.eval()
    assert not hasattr(model, 'talker')
    assert not getattr(model, 'is_quantized', False)
    write('model-ready.json', {'revision':REV, 'dtype':str(model.dtype), 'quantized':False,
        'device':str(model.device), 'gpu':torch.cuda.get_device_name(0),
        'gpu_total_bytes':torch.cuda.get_device_properties(0).total_memory,
        'gpu_allocated_bytes':torch.cuda.memory_allocated(0), 'loading_seconds':time.time()-started,
        'original_index_sha256':original_index_sha, 'derived_index_sha256':sha(index_file),
        'shard_sha256':SHARDS, 'native_gpt_hearing':False, 'private_audio_uploaded':False})
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
        conversation = [{'role':'system','content':[{'type':'text','text':
            'You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group, capable of perceiving auditory and visual inputs, as well as generating text and speech.'}]},
            {'role':'user','content':[{'type':'audio','audio':'local-audio-input'},
                                    {'type':'text','text':PROMPT}]}]
        text = processor.apply_chat_template(conversation, add_generation_prompt=True, tokenize=False)
        inputs = processor(text=text, audio=[y], sampling_rate=rate,
                           return_tensors='pt', padding=True).to('cuda:0')
        for name, value in inputs.items():
            if torch.is_floating_point(value): inputs[name] = value.to(torch.float16)
        begin = time.time()
        with torch.inference_mode():
            output = model.generate(**inputs, do_sample=False, max_new_tokens=160,
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

