"""Disposable FREE_ONLY Qwen3 Omni NF4 qualification on public synthetic audio."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path('/kaggle/working')
OUT = ROOT / 'true-sound-qwen3-30b-nf4-r1'
OUT.mkdir(exist_ok=False)
REV = '26291f793822fb6be9555850f06dfe95f2d7e695'
MODEL = 'Qwen/Qwen3-Omni-30B-A3B-Instruct'
DOWNLOAD_BYTES = 64972981856
SHARDS = {
    'model-00001-of-00015.safetensors':'f95d142b727fbd0698f0ed9478e222d4f29467df855e21862e46bd1401049065',
    'model-00002-of-00015.safetensors':'320c1f31f7ddc4efd2501891590eca2c481ce4eca3db33d70ebbb637dae85764',
    'model-00003-of-00015.safetensors':'306f06b05ef032f1fa51eb62e72c3432324e7a084fa0d15ed17ff856adffcf33',
    'model-00004-of-00015.safetensors':'4cb551f433bfb4d83a5843e433e74688d71a96eeb1b62217b37d719026d559b5',
    'model-00005-of-00015.safetensors':'8aec5e8cc0e0b179a81f690af31a1149238f4b1d18ac60e3f690020fdf7d915f',
    'model-00006-of-00015.safetensors':'8ff40a3d9e9c59a35a10257c1c5b216f472e6a102a4d6059bd31183eee03cb4c',
    'model-00007-of-00015.safetensors':'f6d84cc1d47178850f9ba1fe9c01f45ee63d9a8b9975f92821ee2b4a0387860b',
    'model-00008-of-00015.safetensors':'9f369ccdc9d2d2a55df794005b23cdbce44494a72e4a0069a150ae471cfea720',
    'model-00009-of-00015.safetensors':'980f754b21c4b20f36e02d184b792f5625f7c9d24b8a5c9da94287cf3cfde11b',
    'model-00010-of-00015.safetensors':'5c5a798376321d74df2eb3f235e1c8c68669f09b0c753b5698a16e681204d808',
    'model-00011-of-00015.safetensors':'6f7c051bd391c89279b43e7342ff4a243ad2ba2144f4aa62233fd2b02d72fce0',
    'model-00012-of-00015.safetensors':'a8b09a9367cd31ebf928e87b9eaf002492379d9d21d352b480854c2fbe6d9978',
    'model-00013-of-00015.safetensors':'d9b7441c3a33e066d109cd6338e74ed680de9aa407d4df66eba5cb3c15c6d738',
}
PROMPT = ('Describe the audible sounds, their texture, and how often they occur. '
          'Give approximate start and end times for discrete events. '
          'State whether there is speech or singing; if unclear, say unclear.')


def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def write(name, obj):
    (OUT/name).write_text(json.dumps(obj,indent=2))
    print(name,json.dumps(obj),flush=True)


def main():
    subprocess.run([sys.executable,'-m','pip','install','--quiet',
        'transformers==4.57.1','huggingface-hub==0.36.0','kernels==0.10.1',
        'bitsandbytes==0.48.1','accelerate==1.11.0','soundfile','librosa'],check=True,timeout=300)
    import numpy as np
    import torch
    import soundfile as sf
    import transformers
    import bitsandbytes as bnb
    from accelerate import init_empty_weights
    from huggingface_hub import snapshot_download
    from transformers import (Qwen3OmniMoeConfig,Qwen3OmniMoeProcessor,
        Qwen3OmniMoeThinkerForConditionalGeneration,BitsAndBytesConfig)
    from transformers.integrations.bitsandbytes import replace_with_bnb_linear
    assert torch.cuda.is_available() and torch.cuda.device_count()>=2,'TWO_GPUS_REQUIRED_NO_CPU_FALLBACK'
    torch.set_num_threads(2)
    gpus=[{'name':torch.cuda.get_device_name(i),'total_bytes':torch.cuda.get_device_properties(i).total_memory,
           'free_bytes':torch.cuda.mem_get_info(i)[0]} for i in range(2)]
    tiny=bnb.nn.Linear4bit(64,64,bias=False,compute_dtype=torch.float16,quant_type='nf4',compress_statistics=True).to('cuda:0')
    with torch.inference_mode():z=tiny(torch.ones((1,64),device='cuda:0',dtype=torch.float16))
    assert torch.isfinite(z).all(),'ACTUAL_CUDA_NF4_NONFINITE'
    del tiny,z
    torch.cuda.empty_cache()
    cache=pathlib.Path('/root/.cache/true-sound-qwen3-hf');cache.mkdir(parents=True,exist_ok=True)
    free_disk=shutil.disk_usage(cache).free
    config_dir=pathlib.Path(snapshot_download(MODEL,revision=REV,cache_dir=str(cache),
        allow_patterns=['*.json','*.txt','*.jinja','*.model','*.tiktoken','LICENSE'],max_workers=2))
    cfg=Qwen3OmniMoeConfig.from_pretrained(config_dir)
    index_file=config_dir/'model.safetensors.index.json'
    original_index_sha=sha(index_file)
    original_index=json.loads(index_file.read_text())
    thinker_map={k:v for k,v in original_index['weight_map'].items() if k.startswith('thinker.')}
    assert set(thinker_map.values())==set(SHARDS),'PINNED_SHARD_LIST_MISMATCH'
    q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,llm_int8_skip_modules=['audio_tower','visual','lm_head'])
    with init_empty_weights():meta=Qwen3OmniMoeThinkerForConditionalGeneration(cfg.thinker_config)
    assert {k.removeprefix('thinker.') for k in thinker_map}==set(meta.state_dict()),'CHECKPOINT_META_KEYS_MISMATCH'
    before={n:m.weight.numel() for n,m in meta.named_modules() if isinstance(m,torch.nn.Linear) and '.experts.' in n}
    meta=replace_with_bnb_linear(meta,modules_to_not_convert=['audio_tower','visual','lm_head'],quantization_config=q)
    after={n:m.weight.numel() for n,m in meta.named_modules() if isinstance(m,bnb.nn.Linear4bit) and '.experts.' in n}
    assert before and before==after,'EXPERT_QUANTIZATION_INCOMPATIBLE'
    qids={id(m.weight) for m in meta.modules() if isinstance(m,bnb.nn.Linear4bit)}
    qnum=sum(p.numel() for p in meta.parameters() if id(p) in qids)
    fullnum=sum(p.numel() for p in meta.parameters() if id(p) not in qids)
    estimate=int(qnum*.65+fullnum*2)
    del meta
    ready=free_disk>=DOWNLOAD_BYTES+12*1024**3 and sum(g['free_bytes'] for g in gpus)>=estimate+4*1024**3
    write('preflight.json',{'revision':REV,'gpus':gpus,'free_cache_disk_bytes':free_disk,
        'weight_download_bytes':DOWNLOAD_BYTES,'estimated_weight_bytes':estimate,'all_expert_linears_replaced':True,
        'expert_modules':len(after),'actual_tiny_cuda_nf4_finite':True,'transformers':transformers.__version__,
        'bitsandbytes':bnb.__version__,'model_download_authorized_by_resources':ready,
        'private_audio_uploaded':False,'qualification':'RESOURCE_COMPATIBILITY_ONLY'})
    assert ready,'RESOURCES_INSUFFICIENT_NO_WEIGHT_DOWNLOAD'
    model_dir=pathlib.Path(snapshot_download(MODEL,revision=REV,cache_dir=str(cache),
        allow_patterns=['*.json','*.txt','*.jinja','*.model','*.tiktoken','LICENSE']+list(SHARDS),max_workers=4))
    for name,expected in SHARDS.items():assert sha(model_dir/name)==expected,'PINNED_WEIGHT_HASH_MISMATCH'
    write('download-ready.json',{'revision':REV,'verified_shard_sha256':SHARDS,'bytes':DOWNLOAD_BYTES})
    original_index['weight_map']=thinker_map
    index_file.write_text(json.dumps(original_index,indent=2))
    processor=Qwen3OmniMoeProcessor.from_pretrained(model_dir)
    start=time.time()
    model=Qwen3OmniMoeThinkerForConditionalGeneration.from_pretrained(model_dir,config=cfg.thinker_config,
        torch_dtype=torch.float16,quantization_config=q,device_map='auto',max_memory={0:'14GiB',1:'14GiB'},
        attn_implementation='sdpa',low_cpu_mem_usage=True)
    assert not hasattr(model,'talker') and model.is_quantized
    assert all(str(d) not in ['cpu','disk'] for d in model.hf_device_map.values()),'OFFLOAD_NOT_QUALIFIED'
    assert sum(isinstance(m,bnb.nn.Linear4bit) and '.experts.' in n for n,m in model.named_modules())==len(after)
    model.eval()
    write('model-ready.json',{'revision':REV,'quantized':True,'quantization':q.to_dict(),
        'device_map':{k:str(v) for k,v in model.hf_device_map.items()},'gpus':gpus,
        'gpu_allocated_bytes':[torch.cuda.memory_allocated(i) for i in range(2)],
        'loading_seconds':time.time()-start,'original_index_sha256':original_index_sha,
        'derived_index_sha256':sha(index_file),'expert_modules_quantized':len(after),
        'private_audio_uploaded':False,'native_gpt_hearing':False})
    rate=16000;count=6*rate
    rng=np.random.default_rng(20261013)
    noise=np.zeros(count,dtype=np.float32);noise[int(.5*rate):int(5.5*rate)]=rng.normal(0,.11,5*rate)
    chirps=np.zeros(count,dtype=np.float32)
    for start in [.6,2.6,4.6]:
        t=np.arange(int(.5*rate))/rate
        tone=.35*np.sin(2*np.pi*(500*t+600*t*t))
        tone*=np.sin(np.pi*np.arange(len(t))/len(t))**2
        chirps[int(start*rate):int(start*rate)+len(t)]=tone
    expected={'a':'14065c57f6151748cb755d63c3020c3ef1dcebe608caa413708e8ea3de06b180',
              'b':'3beb3c2fcd75a1ecae2eb908773af860b46075dd51954cd11d818eeb9e648009'}
    input_device=model.model.embed_tokens.weight.device
    for sid,audio in [('a',chirps),('b',noise)]:
        wav=OUT/(sid+'.wav');sf.write(wav,audio,rate,subtype='PCM_16');assert sha(wav)==expected[sid]
        y,sr=sf.read(wav,dtype='float32')
        conv=[{'role':'system','content':[{'type':'text','text':'You are a helpful assistant.'}]},
              {'role':'user','content':[{'type':'audio','audio':'local-audio-input'},{'type':'text','text':PROMPT}]}]
        text=processor.apply_chat_template(conv,add_generation_prompt=True,tokenize=False)
        inputs=processor(text=text,audio=[y],sampling_rate=rate,return_tensors='pt',padding=True).to(input_device)
        for name,value in inputs.items():
            if torch.is_floating_point(value):inputs[name]=value.to(torch.float16)
        begin=time.time()
        with torch.inference_mode():
            output=model.generate(**inputs,do_sample=False,max_new_tokens=200,
                eos_token_id=processor.tokenizer.eos_token_id,pad_token_id=processor.tokenizer.pad_token_id)
        tail=output[:,inputs['input_ids'].shape[1]:]
        write(sid+'-receipt.json',{'sample_id':sid,'input_sha256':sha(wav),'model_input_samples':len(y),
            'model_input_rate':sr,'input_feature_shape':list(inputs['input_features'].shape),
            'feature_attention_valid_frames':inputs['feature_attention_mask'].sum(-1).tolist(),
            'answer':processor.batch_decode(tail,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0],
            'prompt':PROMPT,'generated_ids':tail[0].tolist(),'eos_id':processor.tokenizer.eos_token_id,
            'seconds':time.time()-begin,'actual_model_input':True,
            'qualification':'UNADJUDICATED_PUBLIC_SYNTHETIC_OBSERVATION'})
    write('frozen-results.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file()})


if __name__=='__main__':
    try:main()
    except Exception as error:
        write('failure.json',{'type':type(error).__name__,'message':str(error)[:1500],
                              'qualification':'NO_AUDIO_INPUT_QUALIFICATION'})
        raise
