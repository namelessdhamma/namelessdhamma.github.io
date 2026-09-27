export default function handler(req,res){
  const configured=Boolean((process.env.ND_TELEGRAM_PUBLISHER_BOT_TOKEN||"").trim()&&(process.env.ND_TELEGRAM_CHANNEL_ID||"").trim()&&(process.env.ND_TELEGRAM_MCP_PATH_TOKEN||"").trim());
  const writes=/^(1|true|yes|on)$/i.test(process.env.ND_TELEGRAM_WRITES_ENABLED||"false");
  res.status(200).json({ok:true,service:"nd-telegram-publisher-vercel-reserve",provider:"vercel",configured,writes});
}