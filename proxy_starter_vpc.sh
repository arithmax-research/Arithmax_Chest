# Copy license to root location
cp ~/.kx/kc.lic /root/.kx/kc.lic

# Start q with -u 0 for remote access
cd ~/codechest/achest
nohup q achest-kdb-q/qserver_proxy.q -p 5001 -u 0 > /tmp/qproxy.log 2>&1 &
echo "qproxy started, PID: $!"

# Verify
ss -tlnp | grep 5001
