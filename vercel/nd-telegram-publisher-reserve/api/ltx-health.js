export default function handler(req,res){
  const state={
    ok:true,
    service:"nd-vercel-shared-reserve",
    capability:"kaggle-ltx",
    provider:"vercel",
    configured:{
      kaggle_api_token:Boolean((process.env.KAGGLE_API_TOKEN||"").trim()),
      kaggle_username:Boolean((process.env.KAGGLE_USERNAME_SLUG||"").trim()),
      ltx_input_token:Boolean((process.env.ND_LTX_INPUT_TOKEN||"").trim()),
      drive_bridge_token:Boolean((process.env.ND_DRIVE_BRIDGE_TOKEN||"").trim())
    },
    mode:"nonblocking-reserve",
    cost_policy:"FREE_ONLY"
  };
  res.status(200).json(state);
}
