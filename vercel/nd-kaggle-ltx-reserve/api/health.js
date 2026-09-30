import {health} from "../lib/ltx-core.js";
export default function handler(req,res){
  res.status(200).json({...health(),service:"nd-kaggle-ltx-reserve",provider:"vercel",anti_hang_release:"NAM-397-v1",control_contract_version:"1",auth_configured:Boolean((process.env.ND_LTX_MCP_PATH_TOKEN||"").trim())});
}
