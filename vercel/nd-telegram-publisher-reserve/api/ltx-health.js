import {health} from "../lib/ltx-core.js";
export default function handler(req,res){
  res.status(200).json({...health(),service:"nd-vercel-shared-reserve",provider:"vercel",auth_configured:Boolean((process.env.ND_LTX_MCP_PATH_TOKEN||process.env.ND_TELEGRAM_MCP_PATH_TOKEN||"").trim())});
}
