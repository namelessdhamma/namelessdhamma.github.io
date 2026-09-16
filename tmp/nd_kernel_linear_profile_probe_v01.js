// ND Kernel Linear persistent-profile qualification v0.1
// Run inside a Kernel Playwright browser launched with profile.name="nd-linear"
// and profile.save_changes=true.
const url = page.url();
let title = "";
let body = "";
try { title = await page.title(); } catch {}
try { body = await page.locator("body").innerText({ timeout: 10000 }); } catch {}

const workspaceVisible =
  /Nameless Dhamma/i.test(body) ||
  /namelessdhamma/i.test(url);

const loginVisible =
  /log in|sign in|continue with google|continue with email/i.test(body);

return {
  ok: workspaceVisible && !loginVisible,
  route: "kernel",
  provider: "linear",
  profile: "nd-linear",
  url,
  title,
  workspaceVisible,
  loginVisible,
  expectedWorkspace: "Nameless Dhamma",
  expectedAccount: "namelessdhamma@gmail.com"
};
