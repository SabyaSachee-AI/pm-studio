# PM Studio website — static, zero dependencies

Serve with nginx on the VPS (e.g. port 8092):

```nginx
server { listen 8092; root /opt/apps/pm-studio/pmStudio_website; index index.html; }
```

Then `sudo nginx -t && sudo systemctl reload nginx`. No build step — edit index.html and refresh.
