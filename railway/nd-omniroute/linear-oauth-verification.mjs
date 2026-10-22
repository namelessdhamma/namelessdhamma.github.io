/**
 * Linear OAuth2 Setup Verification Helper
 * 
 * Run this after setting Railway variables to verify OAuth configuration.
 * Usage: node linear-oauth-verification.mjs
 * 
 * Never logs or prints secret values.
 */

function redact(value) {
  if (!value) return '[empty]';
  const s = String(value);
  if (s.includes('Bearer') || s.includes('sk_') || s.includes('ghp_')) return '[REDACTED]';
  return s;
}

function checkVariable(name, isSensitive = false) {
  const value = process.env[name];
  const status = value ? '✓' : '✗';
  const display = isSensitive ? '[REDACTED]' : (value || '[not set]');
  console.log(`  ${status} ${name}: ${display}`);
  return !!value;
}

async function verify() {
  console.log('=== Linear OAuth2 Railway Variables Verification ===\n');

  console.log('Checking required variables:\n');
  
  const checks = {
    api_key: checkVariable('ND_LINEAR_API_KEY', true),
    app_id: checkVariable('ND_LINEAR_OAUTH_APP_ID'),
    client_id: checkVariable('ND_LINEAR_OAUTH_CLIENT_ID'),
    client_secret: checkVariable('ND_LINEAR_OAUTH_CLIENT_SECRET', true),
    scope: checkVariable('ND_LINEAR_OAUTH_SCOPE')
  };

  const redirect = process.env.ND_LINEAR_OAUTH_REDIRECT_URI;
  console.log(`  ${redirect ? '✓' : '?'} ND_LINEAR_OAUTH_REDIRECT_URI: ${redirect || '[not set—auto-generated]'}`);

  console.log('\nConfiguration Summary:\n');
  
  const config = {
    'API Key configured': checks.api_key,
    'OAuth App ID set': checks.app_id,
    'OAuth Client ID set': checks.client_id,
    'Client Secret set': checks.client_secret,
    'Scopes configured': checks.scope && process.env.ND_LINEAR_OAUTH_SCOPE === 'read,write'
  };

  for (const [key, value] of Object.entries(config)) {
    console.log(`  ${value ? '✓' : '✗'} ${key}`);
  }

  const allSet = Object.values(checks).every(v => v);
  
  console.log(`\nStatus: ${allSet ? '✓ Ready for deployment' : '✗ Missing variables'}`);

  if (!allSet) {
    console.log('\nNext steps:');
    console.log('1. Open https://linear.app/settings/api');
    console.log('2. Create OAuth app: "ND Navigator Resilience"');
    console.log('3. Copy Client ID and Secret');
    console.log('4. Set Railway variables:');
    if (!checks.app_id) console.log('   - ND_LINEAR_OAUTH_APP_ID=<from-linear>');
    if (!checks.client_id) console.log('   - ND_LINEAR_OAUTH_CLIENT_ID=<from-linear>');
    if (!checks.client_secret) console.log('   - ND_LINEAR_OAUTH_CLIENT_SECRET=<from-linear>');
    console.log('5. Redeploy nd-external-intelligence');
    process.exit(1);
  }

  console.log('\nTo test after deployment:');
  console.log('  curl https://nd-external-intelligence-production.up.railway.app/linear/health');
  console.log('  curl https://nd-external-intelligence-production.up.railway.app/linear/oauth/status');
}

verify().catch(e => {
  console.error('Error:', String(e.message || e));
  process.exit(1);
});

