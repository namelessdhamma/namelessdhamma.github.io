import { driveHealth } from '../drive_core.mjs';

export default async function handler(req,res){
  res.setHeader('cache-control','no-store');
  if(req.method!=='GET') return res.status(405).json({ok:false,error:'method_not_allowed'});
  try{
    return res.status(200).json(await driveHealth());
  }catch(e){
    return res.status(503).json({
      ok:false,
      service:'ND Drive Reserve Vercel',
      error:String(e?.message||e).slice(0,800)
    });
  }
}
