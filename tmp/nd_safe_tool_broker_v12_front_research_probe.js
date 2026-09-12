import { Buffer } from "node:buffer";
const SRC="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js";
let s=await (await fetch(SRC)).text();
const oldBase='const BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/d519ae887c5d7a972b9dc676eef58c964cd6c6b0/tmp/nd_safe_tool_broker_v9_father_comment.js";';
const newBase='const BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/d91e47c6f4a975a28dd88507f416c74d8bbc9e5a/tmp/nd_safe_tool_broker_v10_research_probe.js";';
if(!s.includes(oldBase))throw new Error("v12 front base marker missing");
s=s.replace(oldBase,newBase);
await import("data:text/javascript;base64,"+Buffer.from(s).toString("base64"));
