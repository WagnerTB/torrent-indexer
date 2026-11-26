const STYLE = `
#hx-fab{position:fixed;right:20px;bottom:calc(20px + env(safe-area-inset-bottom));z-index:99999;display:inline-flex;align-items:center;gap:8px;border:0;border-radius:999px;padding:12px 18px;background:linear-gradient(135deg,#1f6feb,#7b2ff7);color:#fff;font:600 13px/1 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.5);cursor:pointer}
#hx-fab:hover{filter:brightness(1.08)}
#hx-fab:focus-visible{outline:2px solid #93c5fd;outline-offset:2px}
#hx-fab-badge{display:none;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:rgba(255,255,255,.24);font-size:11px;line-height:1}
.hx-backdrop{position:fixed;inset:0;z-index:99998;background:rgba(0,0,0,.62);backdrop-filter:blur(2px)}
.hx-backdrop[hidden]{display:none!important}
.hx-shell{position:fixed;z-index:99999;left:50%;top:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;width:min(1040px,calc(100vw - 32px));height:86vh;height:86dvh;max-height:920px;background:#111113;border:1px solid #2c2c30;border-radius:14px;box-shadow:0 24px 80px rgba(0,0,0,.7);overflow:hidden;color:#eee;font:13px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.hx-shell[hidden]{display:none!important}
.hx-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px 10px;border-bottom:1px solid #232327}
.hx-head-title{font:650 16px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#fff;margin:0}
.hx-head-sub{display:block;color:#a1a1aa;font:12px system-ui;margin-top:3px}
.hx-icon-btn{appearance:none;border:1px solid #333338;background:#1a1a1d;color:#c9ccd1;border-radius:9px;width:38px;height:38px;font:22px/1 system-ui;cursor:pointer;display:grid;place-items:center}
.hx-icon-btn:hover{background:#252529;color:#fff}
.hx-tabs{display:flex;gap:4px;padding:8px 14px 0;border-bottom:1px solid #232327;overflow-x:auto;scrollbar-width:none;flex:0 0 auto}
.hx-tabs::-webkit-scrollbar{display:none}
.hx-tab{appearance:none;border:0;border-bottom:2px solid transparent;background:transparent;color:#9aa0a6;padding:10px 14px;border-radius:8px 8px 0 0;font:600 13px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:7px}
.hx-tab:hover{color:#e5e7eb;background:#17171a}
.hx-tab[aria-selected="true"]{color:#fff;background:#19191c;border-bottom-color:#60a5fa}
.hx-tab:focus-visible{outline:2px solid #3b82f6;outline-offset:-2px}
.hx-tab-count{display:flex;align-items:center;justify-content:center;min-width:19px;height:19px;padding:0 5px;border-radius:999px;background:#2a2a30;color:#c9ccd1;font-size:10px}
.hx-tab-count[hidden]{display:none!important}
.hx-body{flex:1 1 auto;overflow:auto;padding:16px 18px 26px;overscroll-behavior:contain;scrollbar-width:thin}
.hx-pane[hidden]{display:none!important}
.hx-muted{color:#9aa0a6}
.hx-warn{color:#f59e0b;white-space:pre-wrap}
.hx-orphan-warn{margin-left:2px;font-size:12px}
.hx-error{color:#f87171;white-space:pre-wrap;margin-top:4px}
.hx-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.hx-input,.hx-select{background:#1a1a1d;border:1px solid #333338;color:#eee;border-radius:8px;padding:8px 10px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:36px;outline:none;min-width:0}
.hx-input{flex:1 1 220px}
.hx-select{flex:0 1 190px}
.hx-input:focus,.hx-select:focus{border-color:#3b82f6;box-shadow:0 0 0 2px rgba(59,130,246,.18)}
.hx-btn{appearance:none;cursor:pointer;border:1px solid #3a3a3f;background:#1d1d21;color:#eee;border-radius:8px;padding:8px 11px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:36px;line-height:1.2}
.hx-btn:hover{background:#252529}
.hx-btn:disabled{opacity:.5;cursor:default}
.hx-btn:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-btn-primary{background:#1f6feb;border-color:#1f6feb;color:#fff}
.hx-btn-primary:hover{background:#2b7bf5}
.hx-btn-ok{background:#1f7a3d;border-color:#1f7a3d;color:#fff}
.hx-btn-ok:hover{background:#248a45}
.hx-quota{border:1px solid #26262b;background:#151518;border-radius:10px;padding:10px 12px;margin-bottom:10px}
.hx-quota-line{font-size:12px;color:#c9ccd1;white-space:pre-wrap}
.hx-bar{height:6px;border-radius:999px;background:#26262b;overflow:hidden;margin:7px 0 0}
.hx-bar>span{display:block;height:100%;background:#60a5fa;width:0;transition:width .3s ease}
.hx-summary{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px}
.hx-chip{appearance:none;cursor:pointer;border:1px solid #2f2f35;background:#17171a;color:#c9ccd1;border-radius:999px;padding:6px 10px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:inline-flex;align-items:center;gap:6px}
.hx-chip:hover{background:#202024}
.hx-chip[aria-pressed="true"]{border-color:#60a5fa;background:rgba(96,165,250,.12);color:#fff}
.hx-chip b{font-weight:700}
.hx-dot{width:7px;height:7px;border-radius:999px;display:inline-block}
.hx-order{position:relative;border:1px solid #26262b;border-radius:10px;background:#151518;padding:11px 12px;margin-bottom:8px}
.hx-order-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.hx-order-side{position:relative;display:flex;align-items:center;gap:8px;flex:0 0 auto}
.hx-kebab{width:34px;height:34px;min-height:34px;padding:0 0 7px;display:grid;place-items:center;border:1px solid #333338;border-radius:9px;background:#1a1a1d;color:#c9ccd1;font:700 20px/1 system-ui;cursor:pointer}
.hx-kebab:hover,.hx-kebab[aria-expanded="true"]{background:#252529;color:#fff;border-color:#3a3a3f}
.hx-kebab:focus-visible{outline:2px solid #3b82f6;outline-offset:2px}
.hx-menu{position:absolute;top:calc(100% + 7px);right:0;z-index:20;width:250px;max-width:calc(100vw - 48px);padding:5px;border:1px solid #35353b;border-radius:10px;background:#1b1b1f;box-shadow:0 18px 48px rgba(0,0,0,.65)}
.hx-menu[hidden]{display:none!important}
.hx-menu-item{display:flex;flex-direction:column;gap:1px;width:100%;padding:8px 10px;border:0;border-radius:7px;background:transparent;color:#f1f2f4;font:600 12.5px/1.3 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-align:left;text-decoration:none;cursor:pointer}
.hx-menu-item:hover,.hx-menu-item:focus-visible{background:#26262b;outline:none;text-decoration:none}
.hx-menu-label{display:block}
.hx-menu-hint{display:block;color:#8f949b;font:400 11px/1.3 system-ui;font-weight:400}
.hx-menu-item-danger .hx-menu-label{color:#fca5a5}
.hx-menu-sep{height:1px;margin:4px;background:#2a2a30}
.hx-ep-panel{margin-top:12px;padding-top:8px;border-top:1px solid #232327}
.hx-ep-toggle{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;padding:8px 9px;border:1px solid #2b2b31;border-radius:8px;background:#131316;color:#e5e7eb;font:600 12px/1.3 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-align:left;cursor:pointer}
.hx-ep-toggle:hover{background:#18181c}
.hx-ep-toggle:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-ep-toggle::before{content:'▸';color:#9aa0a6;font-size:10px;flex:0 0 auto}
.hx-ep-toggle[aria-expanded="true"]::before{content:'▾'}
.hx-ep-toggle-label{flex:1 1 auto;min-width:0}
.hx-ep-toggle-meta{flex:0 0 auto;color:#9aa0a6;font:400 11px/1.3 system-ui}
.hx-ep-panel-body{margin-top:6px}
.hx-ep-panel-body[hidden]{display:none!important}
.hx-ep-pager{display:flex;align-items:center;justify-content:center;gap:4px;margin-top:6px}
.hx-order-title{min-width:0;color:#f1f2f4;font:600 13px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-kind{display:inline-block;color:#a1a1aa;font:600 11px system-ui;text-transform:uppercase;letter-spacing:.04em;margin-right:6px}
.hx-status{flex:0 0 auto;border-radius:999px;padding:3px 8px;font:600 10px system-ui;border:1px solid transparent;white-space:nowrap}
.hx-status-downloaded{color:#4ade80;background:rgba(74,222,128,.11);border-color:rgba(74,222,128,.28)}
.hx-status-partial{color:#2dd4bf;background:rgba(45,212,191,.11);border-color:rgba(45,212,191,.28)}
.hx-status-downloading{color:#60a5fa;background:rgba(96,165,250,.12);border-color:rgba(96,165,250,.3)}
.hx-status-queued{color:#fbbf24;background:rgba(251,191,36,.11);border-color:rgba(251,191,36,.28)}
.hx-status-searching{color:#c084fc;background:rgba(192,132,252,.12);border-color:rgba(192,132,252,.3)}
.hx-status-error{color:#f87171;background:rgba(248,113,113,.12);border-color:rgba(248,113,113,.3)}
.hx-status-missing{color:#a1a1aa;background:rgba(161,161,170,.1);border-color:rgba(161,161,170,.25)}
.hx-order-meta{color:#a1a1aa;font-size:12px;margin-top:3px;overflow-wrap:anywhere}
.hx-order-event{color:#a1a1aa;font-size:12px;margin-top:3px;overflow-wrap:anywhere}
.hx-order-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.hx-order-result{color:#a1a1aa;font-size:12px;margin-top:6px;white-space:pre-wrap;overflow-wrap:anywhere}
#hx-pi-status{margin:1rem 1.25rem .5rem;padding:12px 14px;border:1px solid #26262b;border-radius:12px;background:#151518;color:#e5e7eb}
#hx-pi-status[hidden]{display:none!important}
body.hx-tab-active #hx-pi-status{display:none!important}
#information-widgets .widget-container:has(.information-widget-resource),#information-widgets .information-widget-resource{display:none!important}
.hx-pi-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap}
.hx-pi-title{font:700 14px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#f5f5f5}
.hx-pi-sub{display:block;color:#a7a7ae;font:11px system-ui;margin-top:2px}
.hx-pi-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
.hx-pi-updated{font:12px system-ui;color:#9aa0a6;white-space:nowrap}
.hx-pi-refresh{appearance:none;border:0;background:transparent;color:#60a5fa;cursor:pointer;font:12px system-ui;padding:0;min-height:32px}
.hx-pi-refresh:hover{color:#93c5fd}
.hx-pi-refresh:focus-visible{outline:2px solid #3b82f6;outline-offset:2px;border-radius:4px}
.hx-pi-toggle{appearance:none;cursor:pointer;border:1px solid #2b2b31;background:#17171a;color:#e5e7eb;border-radius:8px;padding:6px 10px;font:600 12px system-ui;min-height:32px}
.hx-pi-toggle:hover{background:#202024}
.hx-pi-toggle:focus-visible{outline:2px solid #e50914;outline-offset:2px}
.hx-pi-summary{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
.hx-pi-summary-item{display:inline-flex;align-items:baseline;gap:5px;border:1px solid #2b2b31;background:#131316;border-radius:999px;padding:5px 10px;min-height:30px}
.hx-pi-summary-label{color:#a7a7ae;font:600 10px system-ui;text-transform:uppercase;letter-spacing:.06em}
.hx-pi-summary-value{color:#f5f5f5;font:700 12px system-ui;font-variant-numeric:tabular-nums}
.hx-pi-tone--ok{color:#4ade80}
.hx-pi-tone--warning{color:#fbbf24}
.hx-pi-tone--critical{color:#f87171}
.hx-pi-tone--unknown{color:#a7a7ae}
.hx-pi-body{margin-top:10px;border-top:1px solid #202024;padding-top:10px}
.hx-pi-body[hidden]{display:none!important}
.hx-pi-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.hx-pi-metric{border:1px solid #232327;border-radius:10px;background:#131316;padding:9px 10px;min-width:0}
.hx-pi-metric-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
.hx-pi-metric-label{color:#a7a7ae;font:600 11px system-ui;text-transform:uppercase;letter-spacing:.05em}
.hx-pi-metric-value{color:#f5f5f5;font:700 13px system-ui;font-variant-numeric:tabular-nums;white-space:nowrap}
.hx-pi-metric-sub{color:#a7a7ae;font:11px system-ui;margin-top:3px;overflow-wrap:anywhere}
.hx-pi-bar{height:6px;border-radius:999px;background:#26262b;overflow:hidden;margin-top:6px}
.hx-pi-bar>span{display:block;height:100%;width:0;background:#4ade80;transition:width .3s ease}
.hx-pi-section-title{display:flex;align-items:center;gap:7px;margin:12px 0 4px;color:#a7a7ae;font:700 10px system-ui;letter-spacing:.08em;text-transform:uppercase}
.hx-pi-section-title::before{content:'';width:3px;height:12px;border-radius:2px;background:#e50914}
.hx-pi-clear{appearance:none;cursor:pointer;margin-top:8px;border:1px solid #3a3a40;background:#1e1e22;color:#f5f5f5;border-radius:7px;padding:5px 9px;font:600 11px system-ui;min-height:30px}
.hx-pi-clear:hover{background:#2a2a31}
.hx-pi-clear:disabled{opacity:.5;cursor:default}
.hx-pi-clear:focus-visible{outline:2px solid #e50914;outline-offset:2px}
.hx-storage-row{padding:8px 0;border-top:1px solid #202024}
.hx-storage-row:first-of-type{border-top:0;padding-top:0}
.hx-storage-line{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.hx-storage-label{min-width:0;font:600 12px system-ui;color:#e5e7eb;overflow-wrap:anywhere}
.hx-storage-kind{display:inline-block;margin-left:6px;color:#a1a1aa;font:600 11px system-ui;text-transform:uppercase;letter-spacing:.04em}
.hx-storage-value{font:12px system-ui;color:#c9ccd1;white-space:nowrap}
.hx-storage-bar{height:7px;border-radius:999px;background:#26262b;overflow:hidden;margin-top:6px}
.hx-storage-bar>span{display:block;height:100%;width:0;background:#4ade80;transition:width .3s ease}
.hx-storage-sub{font:12px system-ui;color:#9aa0a6;margin-top:4px;overflow-wrap:anywhere}
.hx-storage-empty{font:12px system-ui;color:#8f949b;padding:4px 0}
@media(min-width:640px){#hx-pi-status{margin:1rem 2.25rem .5rem}}
.hx-viewbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.hx-seg{display:inline-flex;gap:3px;padding:3px;border:1px solid #333338;border-radius:999px;background:#17171a}
.hx-seg .hx-btn{border:0;border-radius:999px;background:transparent;color:#9aa0a6;min-height:30px;padding:6px 14px}
.hx-seg .hx-btn[aria-pressed="true"]{background:#1f6feb;color:#fff}
.hx-summary[hidden],.hx-history-section[hidden]{display:none!important}
.hx-status-request_pending{color:#fbbf24;background:rgba(251,191,36,.11);border-color:rgba(251,191,36,.28)}
.hx-status-request_approved{color:#60a5fa;background:rgba(96,165,250,.12);border-color:rgba(96,165,250,.3)}
.hx-status-request_declined,.hx-status-request_failed{color:#f87171;background:rgba(248,113,113,.12);border-color:rgba(248,113,113,.3)}
.hx-status-request_completed{color:#4ade80;background:rgba(74,222,128,.11);border-color:rgba(74,222,128,.28)}
.hx-status-requested{color:#fbbf24;background:rgba(251,191,36,.11);border-color:rgba(251,191,36,.28)}
.hx-episode-row{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid #202024}
.hx-episode-main{min-width:0;flex:1 1 auto}
.hx-episode-title{color:#e5e7eb;font:600 12px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-episode-sub{color:#9aa0a6;font-size:12px;margin-top:2px;overflow-wrap:anywhere}
.hx-episode-side{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.hx-sub-summary{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin:0 2px 8px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.hx-sub-summary-actions{display:flex;align-items:center;gap:10px}
.hx-sub-all,.hx-sub-batch{background:transparent;border:0;color:#60a5fa;padding:0;min-height:auto;font:12px system-ui;cursor:pointer}
.hx-sub-batch{font-weight:600}
.hx-sub-all:hover,.hx-sub-batch:hover{background:transparent;color:#93c5fd;text-decoration:underline}
.hx-sub-all:focus-visible,.hx-sub-batch:focus-visible{outline:2px solid #3b82f6;outline-offset:2px;border-radius:4px}
.hx-sub-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hx-sub-toggle{display:flex;align-items:center;gap:8px;flex:1 1 180px;min-width:0;padding:0;border:0;background:transparent;color:inherit;text-align:left;cursor:pointer;font:inherit}
.hx-sub-toggle::before{content:'▸';color:#9aa0a6;font-size:10px;flex:0 0 auto}
.hx-sub-toggle[aria-expanded="true"]::before{content:'▾'}
.hx-sub-toggle:hover .hx-sub-title{color:#fff}
.hx-sub-toggle:focus-visible{outline:2px solid #3b82f6;outline-offset:2px;border-radius:4px}
.hx-sub-text{display:flex;flex-direction:column;min-width:0}
.hx-sub-title{color:#f1f2f4;font:600 13px/1.3 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-sub-meta{color:#9aa0a6;font:11px/1.35 system-ui;margin-top:2px;overflow-wrap:anywhere}
.hx-sub-action{flex:0 0 auto;margin-left:auto}
.hx-sub-body{margin-top:8px;border-top:1px solid #232327;padding-top:2px}
.hx-sub-body[hidden]{display:none!important}
.hx-sub-row{align-items:flex-start}
.hx-sub-main{min-width:0;flex:1 1 auto}
.hx-sub-line{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.hx-sub-code{color:#e5e7eb;font:600 12px system-ui;font-variant-numeric:tabular-nums}
.hx-sub-name{color:#d4d4d8;font:12px system-ui;overflow-wrap:anywhere}
.hx-sub-lang{display:inline-flex;align-items:center;border:1px solid rgba(96,165,250,.28);background:rgba(96,165,250,.1);color:#93c5fd;border-radius:999px;padding:1px 6px;font:600 10px system-ui}
.hx-sub-progress{display:flex;align-items:center;gap:8px;margin-top:8px}
.hx-sub-progress-label{flex:0 0 auto;color:#9aa0a6;font:11px system-ui;white-space:nowrap}
.hx-sub-progress-bar{flex:1 1 auto;height:4px;border-radius:999px;background:#26262b;overflow:hidden}
.hx-sub-progress-bar>span{display:block;height:100%;background:#60a5fa;transition:width .3s ease}
.hx-queue-list{margin:8px 0 2px;border-top:1px solid #232327}
.hx-queue-item{display:flex;align-items:baseline;justify-content:space-between;gap:8px;padding:6px 0;border-bottom:1px solid #202024;font:12px system-ui}
.hx-queue-item-title{min-width:0;color:#e5e7eb;overflow-wrap:anywhere}
.hx-queue-item-meta{flex:0 0 auto;color:#9aa0a6;font-size:11px;white-space:nowrap}
.hx-queue-more{color:#9aa0a6;font-size:11px;padding-top:6px}
.hx-queue-head{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.hx-queue-note{color:#9aa0a6;font:400 11px system-ui}
.hx-queue-body{margin-top:8px}
.hx-ep{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #202024}
.hx-ep-label{min-width:0;color:#d4d4d8;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-ep-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.hx-hist{display:grid;grid-template-columns:92px minmax(0,1fr) auto;gap:4px 12px;align-items:start;border:1px solid #26262b;border-radius:8px;background:#151518;padding:8px 10px;margin-bottom:6px}
.hx-hist-date{font:600 12px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#c9ccd1}
.hx-hist-date-label{display:block;color:#9aa0a6;font:11px system-ui;text-transform:uppercase;letter-spacing:.04em}
.hx-hist-time{display:block;color:#9aa0a6;font:11px system-ui}
.hx-hist-main{min-width:0}
.hx-hist-title{color:#f1f2f4;font:600 12.5px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-hist-meta{color:#a1a1aa;font:12px/1.4 system-ui;margin-top:2px;overflow-wrap:anywhere}
.hx-hist-event{color:#a1a1aa;font:12px/1.4 system-ui;margin-top:2px;overflow-wrap:anywhere}
.hx-hist-side{display:flex;flex-direction:column;align-items:flex-end;gap:5px}
.hx-hist-badges{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end}
.hx-hist-badge{border-radius:999px;padding:2px 7px;font:600 10px system-ui;border:1px solid transparent;white-space:nowrap}
.hx-hist-badge-active{color:#60a5fa;background:rgba(96,165,250,.1);border-color:rgba(96,165,250,.28)}
.hx-hist-badge-archived{color:#c084fc;background:rgba(192,132,252,.1);border-color:rgba(192,132,252,.28)}
.hx-hist-actions{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}
.hx-hist-actions .hx-btn{min-height:32px;padding:5px 9px;font-size:12px}
.hx-empty{padding:28px 10px;text-align:center;color:#a1a1aa;font-size:12px}

.hx-sep{height:1px;background:#232327;margin:12px 0}
@media(max-width:700px){
  #hx-fab{right:14px;bottom:calc(14px + env(safe-area-inset-bottom));padding:11px 16px}
  .hx-shell{left:0;top:0;transform:none;width:100vw;height:100vh;height:100dvh;max-height:none;border-radius:0;border:0}
  .hx-head{padding:12px 14px 8px}
  .hx-tabs{padding:6px 10px 0}
  .hx-tab{flex:1;justify-content:center;padding:11px 8px}
  .hx-body{padding:12px 14px 30px}
  .hx-input{flex:1 1 100%}
  .hx-select{flex:1 1 100%}
  .hx-toolbar .hx-select.hx-compact{flex:1 1 calc(50% - 4px);min-width:0}
  .hx-toolbar .hx-btn{flex:1 1 auto}
  .hx-order{padding:10px}
  .hx-order-side{gap:6px}
  .hx-kebab{width:36px;height:36px;min-height:36px}
  .hx-menu{width:min(250px,calc(100vw - 40px))}
  .hx-status{align-self:flex-start}
  .hx-ep-toggle{padding:9px 10px}
  .hx-ep-toggle-meta{font-size:10px}
  .hx-ep{align-items:flex-start}
  .hx-episode-row{flex-direction:column;gap:5px}
  .hx-episode-side{justify-content:flex-start}
  .hx-seg{width:100%}
  .hx-seg .hx-btn{flex:1 1 auto}
  #hx-pi-status{margin:1rem 1.25rem .5rem;padding:10px 12px}
  .hx-pi-sub{display:none}
  .hx-pi-updated{display:none}
  .hx-pi-metrics{grid-template-columns:1fr}
  .hx-pi-metric-value{white-space:normal}
  .hx-storage-line{flex-direction:column;gap:2px;align-items:flex-start}
  .hx-storage-value{white-space:normal}
  .hx-toolbar .hx-search{order:-2;flex:1 1 55%}
  .hx-toolbar .hx-refresh{order:-1;flex:0 0 auto}
  .hx-summary{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
  .hx-summary::-webkit-scrollbar{display:none}
  .hx-summary .hx-chip{flex:0 0 auto}
  .hx-ep-remove{min-height:40px;padding:8px 10px;font-size:12px}
  .hx-sub-toggle{min-height:40px}
  .hx-sub-action{min-height:40px}
  .hx-ep-actions .hx-btn{min-height:40px;padding:8px 10px}
  .hx-hist{grid-template-columns:1fr;gap:5px;padding:8px 10px}
  .hx-hist-date{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap}
  .hx-hist-date-label,.hx-hist-time{display:inline}
  .hx-hist-side{flex-direction:row;align-items:center;justify-content:space-between}
  .hx-hist-badges{justify-content:flex-start}
  .hx-pi-refresh{padding:6px 8px;border-radius:4px}
  .hx-pi-toggle{padding:6px 8px}
  body.hx-tab-active #information-widgets{margin:8px 8px 0;padding:6px 8px}
  body.hx-tab-active #information-widgets input[type="text"]{padding:8px 10px;font-size:13px;min-height:36px}
  body.hx-tab-active #information-widgets .information-widget-datetime .text-xl{font-size:16px}
  body.hx-tab-active .hx-help{padding:6px 10px;font-size:12px}
  body.hx-tab-active .hx-help summary{padding:1px 0}
}
body.hx-has-nav #inner_wrapper{padding-top:50px!important}
#hx-nav,#hx-nav *,#hx-view,#hx-view *{box-sizing:border-box}
#hx-nav{position:fixed;top:0;left:0;right:0;z-index:35;height:50px;background:rgba(15,15,17,.96);backdrop-filter:blur(8px);border-bottom:1px solid #26262b;box-shadow:0 2px 14px rgba(0,0,0,.28)}
#hx-nav-inner{height:100%;max-width:1536px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:4px;overflow-x:auto;scrollbar-width:none}
#hx-nav-inner::-webkit-scrollbar{display:none}
.hx-nav-tab{display:inline-flex;align-items:center;gap:7px;white-space:nowrap;text-decoration:none;color:#9aa0a6;background:transparent;border:0;border-radius:8px;padding:8px 13px;font:600 13px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;cursor:pointer;transition:background .15s,color .15s}
.hx-nav-tab:hover{color:#e5e7eb;background:#1b1b1f}
.hx-nav-tab[aria-selected="true"]{color:#fff;background:rgba(96,165,250,.14);box-shadow:inset 0 -2px 0 #60a5fa}
.hx-nav-tab:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-nav-count{display:flex;align-items:center;justify-content:center;min-width:19px;height:19px;padding:0 5px;border-radius:999px;background:#2a2a30;color:#c9ccd1;font-size:10px}
.hx-nav-count[hidden]{display:none!important}
#hx-view{width:100%;padding:14px 20px 40px}
#hx-view[hidden]{display:none!important}
.hx-pane[hidden]{display:none!important}
body.hx-tab-active .services-group,
body.hx-tab-active #bookmarks,
body.hx-tab-active #footer{display:none!important}
@media(max-width:700px){
  body.hx-has-nav #inner_wrapper{padding-top:50px!important}
  #hx-nav-inner{padding:0 8px;gap:2px}
  .hx-nav-tab{flex:1;justify-content:center;padding:9px 6px;font-size:12.5px}
  #hx-view{padding:10px 12px 30px}
  .hx-addbody{position:sticky;top:50px;z-index:20;background:#111113}
}
.hx-addbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.hx-addbar[hidden]{display:none!important}
.hx-addbody{border:1px solid #26262b;border-radius:10px;background:#131316;padding:10px 12px;margin-bottom:10px}
.hx-addbody[hidden]{display:none!important}
.hx-addbody .hx-input{flex:1 1 100%;margin-bottom:8px}
.hx-lookup{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #202024}
.hx-lookup:last-child{border-bottom:0;padding-bottom:0}
.hx-lookup-poster{width:46px;height:69px;object-fit:cover;border-radius:6px;background:#1c1c20;flex:0 0 auto}
.hx-lookup-main{min-width:0;flex:1 1 auto}
.hx-lookup-title{color:#f1f2f4;font:600 13px/1.3 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-lookup-meta{color:#a1a1aa;font-size:12px;margin-top:2px;overflow-wrap:anywhere}
.hx-lookup-actions{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px}
.hx-lookup-form{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}
.hx-lookup-form .hx-select{flex:1 1 150px}
.hx-field{display:flex;flex-direction:column;gap:4px;flex:1 1 150px;min-width:0;font:12px system-ui;color:#9aa0a6}
.hx-field .hx-select{flex:1 1 auto}
.hx-season{border:1px solid #26262b;border-radius:10px;margin-bottom:8px;overflow:hidden}
.hx-season[hidden],.hx-ep-row[hidden]{display:none!important}
.hx-season-head{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#17171a;border-bottom:1px solid #26262b;font:600 12px system-ui;color:#e5e7eb;cursor:pointer;list-style:none}
.hx-season-head::-webkit-details-marker{display:none}
.hx-season-head::before{content:'▸';color:#9aa0a6;font-size:11px;flex:0 0 auto;transition:transform .15s}
details[open]>.hx-season-head::before{content:'▾'}
.hx-season-head input,.hx-ep-row input{accent-color:#3b82f6;width:15px;height:15px;flex:0 0 auto;margin:0}
.hx-ep-row{display:flex;align-items:flex-start;gap:8px;padding:7px 10px;border-bottom:1px solid #202024;font:12px system-ui;color:#d4d4d8;cursor:pointer}
.hx-ep-row:last-child{border-bottom:0}
.hx-ep-row:hover{background:#18181b}
.hx-ep-num{color:#9aa0a6;font-variant-numeric:tabular-nums;flex:0 0 auto;min-width:62px}
.hx-ep-name{min-width:0;flex:1 1 auto;overflow-wrap:anywhere}
.hx-ep-tag{flex:0 0 auto;border-radius:999px;padding:2px 7px;font:600 10px system-ui;color:#4ade80;background:rgba(74,222,128,.11);border:1px solid rgba(74,222,128,.28)}
.hx-ep-tag-request{color:#c084fc;background:rgba(192,132,252,.12);border-color:rgba(192,132,252,.3)}
.hx-ep-foot{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 0 0;position:sticky;bottom:0;background:#111113;border-top:1px solid #232327;margin-top:8px}
.hx-check{display:inline-flex;align-items:center;gap:6px;color:#c9ccd1;font:12px system-ui;cursor:pointer}
.hx-check input{accent-color:#3b82f6;width:15px;height:15px;margin:0}
.hx-filters-btn[hidden]{display:none!important}
.hx-filters-btn[data-count]:not([data-count="0"]){border-color:#60a5fa;background:rgba(96,165,250,.12);color:#fff}
.hx-shell-filters{width:min(620px,calc(100vw - 32px));height:auto;max-height:86vh;max-height:86dvh;min-height:0}
.hx-filter-group{margin-bottom:14px}
.hx-filter-label{display:block;color:#c9ccd1;font:600 12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin-bottom:6px}
.hx-filter-chips{display:flex;flex-wrap:wrap;gap:6px}
.hx-filter-status-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
.hx-filter-status-head .hx-filter-label{margin-bottom:0}
.hx-filter-status-actions{display:flex;gap:6px}
.hx-filter-status-actions .hx-btn{min-height:28px;padding:4px 8px;font-size:11px}
.hx-filter-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px 14px;max-height:260px;overflow:auto;padding-right:4px}
.hx-filter-actions{display:flex;align-items:center;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid #232327}
.hx-filter-actions .hx-btn:first-child{margin-right:auto}
.hx-pager{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:4px;margin:14px 0 4px}
.hx-pager[hidden]{display:none!important}
.hx-page{appearance:none;cursor:pointer;border:1px solid #2f2f35;background:#17171a;color:#c9ccd1;border-radius:8px;min-width:34px;min-height:34px;padding:6px 10px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.hx-page:hover{background:#202024}
.hx-page[aria-current="page"]{background:#1f6feb;border-color:#1f6feb;color:#fff}
.hx-page:disabled{opacity:.45;cursor:default}
.hx-page:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-page-info{color:#9aa0a6;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0 6px}
@media(max-width:700px){
  .hx-shell-filters{left:0;top:0;transform:none;width:100vw;height:100vh;height:100dvh;max-height:none;border-radius:0;border:0}
  .hx-filter-grid{grid-template-columns:1fr;max-height:none}
  .hx-filter-actions{position:sticky;bottom:0;background:#111113}
  .hx-page-info{flex:1 1 100%;text-align:center;order:3;margin:4px 0 0}
}
.hx-help{border:1px solid #26262b;background:#151518;border-radius:10px;padding:9px 12px;margin-bottom:10px;color:#c9ccd1;font:12px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.hx-help summary{cursor:pointer;color:#e5e7eb;font-weight:600;outline:none}
.hx-help summary:focus-visible{outline:2px solid #3b82f6;outline-offset:2px;border-radius:4px}
.hx-help ul{margin:8px 0 0 18px;padding:0}
.hx-help li{margin:3px 0}
.hx-view-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hx-btn-link{display:inline-flex;align-items:center;background:transparent;border:0;color:#60a5fa;padding:0;min-height:auto;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-decoration:none}
.hx-btn-link::before{content:'• ';color:#8f949b}
.hx-btn-link:hover{color:#93c5fd;text-decoration:underline}
.hx-btn-link[hidden]{display:none!important}
/* Tema Netflix-like: sobrescreve o chrome; cores de status continuam semânticas. */
#hx-view{background:radial-gradient(900px 420px at 50% -12%,rgba(229,9,20,.12),transparent 62%)}
#hx-fab{background:linear-gradient(135deg,#e50914,#b20710);box-shadow:0 10px 34px rgba(229,9,20,.34),0 8px 30px rgba(0,0,0,.5)}
#hx-fab:focus-visible{outline:2px solid #ff8a90;outline-offset:2px}
.hx-shell{background:#0b0b0d;border-color:#2b2b31;color:#f5f5f5}
.hx-head{border-bottom-color:#232327}
.hx-head-sub{color:#a7a7ae}
.hx-icon-btn{border-color:#2b2b31;background:#1e1e22;color:#a7a7ae}
.hx-icon-btn:hover{background:#2a2a31;color:#fff}
.hx-tabs{border-bottom-color:#232327}
.hx-tab{color:#a7a7ae}
.hx-tab:hover{color:#f5f5f5;background:#17171a}
.hx-tab[aria-selected="true"]{background:#1e1e22;border-bottom-color:#e50914}
.hx-tab-count{background:#2a2a30;color:#a7a7ae}
.hx-muted,.hx-order-meta,.hx-order-event,.hx-order-result,.hx-episode-sub,.hx-sub-meta,.hx-queue-item-meta,.hx-queue-note,.hx-storage-sub,.hx-storage-empty,.hx-pi-sub,.hx-pi-updated,.hx-pi-metric-label,.hx-pi-metric-sub,.hx-pi-summary-label,.hx-hist-meta,.hx-hist-event,.hx-hist-date-label,.hx-hist-time,.hx-lookup-meta,.hx-field,.hx-ep-label,.hx-ep-num,.hx-ep-toggle-meta,.hx-ep-toggle::before,.hx-sub-toggle::before,.hx-sub-progress-label,.hx-queue-more,.hx-page-info,.hx-menu-hint{color:#a7a7ae}
.hx-order-title,.hx-episode-title,.hx-sub-title,.hx-sub-code,.hx-hist-title,.hx-lookup-title,.hx-pi-title,.hx-pi-metric-value,.hx-pi-summary-value,.hx-storage-label,.hx-queue-item-title,.hx-season-head,.hx-help,.hx-help summary,.hx-quota-line,.hx-hist-date,.hx-storage-value,.hx-filter-label,.hx-check{color:#f5f5f5}
.hx-ep-name,.hx-sub-name,.hx-ep-row{color:#d8d8dc}
.hx-input,.hx-select{background:#1e1e22;border-color:#2b2b31;color:#f5f5f5;color-scheme:dark}
.hx-input:focus,.hx-select:focus{border-color:#e50914;box-shadow:0 0 0 2px rgba(229,9,20,.22)}
.hx-btn{background:#1e1e22;border-color:#3a3a40;color:#f5f5f5}
.hx-btn:hover{background:#2a2a31}
.hx-btn-primary{background:#e50914;border-color:#e50914;color:#fff}
.hx-btn-primary:hover{background:#f6121d}
.hx-btn:focus-visible,.hx-icon-btn:focus-visible,.hx-tab:focus-visible,.hx-btn-link:focus-visible,.hx-page:focus-visible,.hx-help summary:focus-visible,.hx-sub-all:focus-visible,.hx-sub-batch:focus-visible,.hx-ep-toggle:focus-visible,.hx-sub-toggle:focus-visible,.hx-kebab:focus-visible,.hx-nav-tab:focus-visible,.hx-pi-refresh:focus-visible,.hx-pi-toggle:focus-visible,.hx-fab:focus-visible{outline-color:#e50914}
.hx-quota,.hx-order,.hx-help,.hx-hist,#hx-pi-status,.hx-addbody,.hx-season{background:#17171a;border-color:#26262b}
.hx-pi-metric,.hx-pi-summary-item{background:#131316;border-color:#26262b}
.hx-pi-toggle{background:#1e1e22;border-color:#3a3a40;color:#f5f5f5}
.hx-pi-toggle:hover{background:#2a2a31}
.hx-quota-line{color:#d8d8dc}
.hx-bar{background:#26262b}
.hx-bar>span{background:#e50914}
.hx-chip{border-color:#2b2b31;background:#17171a;color:#a7a7ae}
.hx-chip:hover{background:#202024}
.hx-chip[aria-pressed="true"]{border-color:#e50914;background:rgba(229,9,20,.13);color:#fff}
.hx-order{background:linear-gradient(180deg,#19191c,#151517);border-color:#232327}
.hx-kind{color:#e50914}
.hx-kebab{border-color:#2b2b31;background:#1e1e22;color:#a7a7ae}
.hx-kebab:hover,.hx-kebab[aria-expanded="true"]{background:#2a2a31;color:#fff;border-color:#3a3a40}
.hx-menu{border-color:#35353c;background:#1c1c21}
.hx-menu-item{color:#f5f5f5}
.hx-menu-item:hover,.hx-menu-item:focus-visible{background:#27272e}
.hx-menu-hint{color:#8f949b}
.hx-menu-sep{background:#2b2b31}
.hx-ep-panel{border-top-color:#232327}
.hx-ep-toggle{border-color:#2b2b31;background:#131316;color:#f5f5f5}
.hx-ep-toggle:hover{background:#18181c}
.hx-pi-refresh{color:#e50914}
.hx-pi-refresh:hover{color:#f6121d}
.hx-seg{border-color:#2b2b31;background:#17171a}
.hx-seg .hx-btn{color:#a7a7ae}
.hx-seg .hx-btn[aria-pressed="true"]{background:#e50914;color:#fff}
.hx-episode-row{border-top-color:#232327}
.hx-sub-all,.hx-sub-batch{color:#e50914}
.hx-sub-all:hover,.hx-sub-batch:hover{color:#f6121d}
.hx-sub-body{border-top-color:#232327}
.hx-sub-lang{border-color:rgba(229,9,20,.28);background:rgba(229,9,20,.1);color:#ff9aa0}
.hx-sub-progress-bar{background:#26262b}
.hx-sub-progress-bar>span{background:#e50914}
.hx-queue-list{border-top-color:#232327}
.hx-queue-item{border-bottom-color:#232327}
.hx-ep{border-bottom-color:#232327}
.hx-ep-label{color:#d8d8dc}
.hx-hist{background:#17171a;border-color:#232327}
.hx-hist-date{color:#d8d8dc}
.hx-hist-actions .hx-btn{background:#1e1e22;border-color:#3a3a40}
.hx-empty{color:#a7a7ae}
.hx-sep{background:#232327}
#hx-nav{background:rgba(11,11,13,.94);border-bottom-color:#232327;box-shadow:0 2px 14px rgba(0,0,0,.35)}
.hx-nav-tab{color:#a7a7ae}
.hx-nav-tab:hover{color:#f5f5f5;background:#1c1c21}
.hx-nav-tab[aria-selected="true"]{color:#fff;background:rgba(229,9,20,.13);box-shadow:inset 0 -2px 0 #e50914}
.hx-nav-count{background:#2a2a30;color:#a7a7ae}
.hx-addbody{background:#131316;border-color:#26262b}
.hx-lookup{border-bottom-color:#232327}
.hx-lookup-poster{background:#1e1e22}
.hx-season-head{background:#17171a;border-bottom-color:#26262b}
.hx-season-head input,.hx-ep-row input,.hx-check input{accent-color:#e50914}
.hx-ep-row{border-bottom-color:#232327}
.hx-ep-row:hover{background:#18181c}
.hx-ep-foot{background:#0b0b0d;border-top-color:#232327}
.hx-check{color:#d8d8dc}
.hx-filters-btn[data-count]:not([data-count="0"]){border-color:#e50914;background:rgba(229,9,20,.13);color:#fff}
.hx-filter-actions{border-top-color:#232327}
.hx-page{border-color:#2b2b31;background:#17171a;color:#a7a7ae}
.hx-page:hover{background:#202024}
.hx-page[aria-current="page"]{background:#e50914;border-color:#e50914;color:#fff}
.hx-help{color:#a7a7ae}
.hx-btn-link{color:#e50914}
.hx-btn-link:hover{color:#f6121d}
.hx-warn{color:#f5a623}
.hx-filter-actions{background:#0b0b0d}
.hx-admin{display:flex;flex-direction:column;gap:14px;color:#e5e7eb}
.hx-admin-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
.hx-admin-title{margin:0;font:700 22px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#fff}
.hx-admin-sub{color:#a1a1aa;font:12px system-ui;margin-top:4px}
.hx-admin-head-actions{display:flex;gap:8px;flex-wrap:wrap}
.hx-admin-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.hx-admin-stat{display:flex;flex-direction:column;gap:2px;padding:10px 12px;border:1px solid #26262b;border-radius:10px;background:#131316}
.hx-admin-stat-value{font:700 20px/1.1 system-ui;color:#fff}
.hx-admin-stat-label{font:11px system-ui;color:#a1a1aa;text-transform:uppercase;letter-spacing:.04em}
.hx-admin-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.hx-admin-search{flex:1 1 220px;min-width:0}
.hx-admin-filter{flex:0 1 180px}
.hx-admin-updated{color:#8b8b93;font:11px system-ui;white-space:nowrap}
.hx-admin-error{margin:0;padding:10px 12px;border:1px solid #7f1d1d;border-radius:10px;background:#2a1111;color:#fecaca;font:12px system-ui;white-space:pre-wrap}
.hx-admin-list{display:flex;flex-direction:column;gap:8px}
.hx-admin-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px;border:1px solid #26262b;border-radius:11px;background:#17171a}
.hx-admin-main{min-width:0;flex:1 1 auto;display:flex;flex-direction:column;gap:3px}
.hx-admin-name{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font:650 14px system-ui;color:#fff}
.hx-admin-dot{width:8px;height:8px;border-radius:999px;background:#a1a1aa;flex:0 0 auto;box-shadow:0 0 0 3px rgba(161,161,170,.12)}
.hx-admin-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;color:#c9ccd1;font:11.5px system-ui;line-height:1.35;min-width:0}
.hx-admin-meta--muted{color:#8b8b93}
.hx-admin-sep{color:#4b4b52}
.hx-admin-badge{padding:2px 7px;border-radius:999px;border:1px solid #5a3a12;background:#2a1b09;color:#fbbf24;font:600 10px system-ui;text-transform:uppercase;letter-spacing:.03em}
.hx-admin-badge--lock{border-color:#3a3a40;background:#1e1e22;color:#a1a1aa}
.hx-admin-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px;flex-wrap:wrap;flex:0 0 auto}
.hx-admin-actions .hx-btn{min-height:34px;padding:7px 10px}
.hx-admin-ok{background:#14351f;border-color:#1f6b3a;color:#bbf7d0}
.hx-admin-ok:hover{background:#1a4227}
.hx-admin-danger{background:#3a1414;border-color:#7f1d1d;color:#fecaca}
.hx-admin-danger:hover{background:#4a1818}
.hx-admin-busy{color:#8b8b93;font:11px system-ui}
.hx-admin-empty{padding:18px;border:1px dashed #2c2c30;border-radius:10px;color:#8b8b93;font:12px system-ui;text-align:center}
.hx-admin-section-title{margin:4px 0 0;font:650 13px system-ui;color:#d8d8dc}
.hx-admin-audit{display:flex;flex-direction:column;border:1px solid #26262b;border-radius:10px;background:#131316;overflow:hidden}
.hx-admin-audit-row{display:grid;grid-template-columns:minmax(140px,1fr) minmax(0,2fr) auto;gap:10px;align-items:center;padding:9px 12px;border-bottom:1px solid #232327;font:11.5px system-ui}
.hx-admin-audit-row:last-child{border-bottom:0}
.hx-admin-audit-time{color:#8b8b93;white-space:nowrap}
.hx-admin-audit-text{color:#d8d8dc;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hx-admin-audit-result{font-weight:600}
.hx-admin-tone--ok{color:#4ade80}
.hx-admin-dot.hx-admin-tone--ok{background:#4ade80;box-shadow:0 0 0 3px rgba(74,222,128,.14)}
.hx-admin-tone--warn{color:#fbbf24}
.hx-admin-dot.hx-admin-tone--warn{background:#fbbf24;box-shadow:0 0 0 3px rgba(251,191,36,.14)}
.hx-admin-tone--bad{color:#f87171}
.hx-admin-dot.hx-admin-tone--bad{background:#f87171;box-shadow:0 0 0 3px rgba(248,113,113,.14)}
.hx-admin-tone--stopped{color:#a1a1aa}
.hx-admin-dot.hx-admin-tone--stopped{background:#6b7280;box-shadow:0 0 0 3px rgba(107,114,128,.12)}
.hx-admin-tone--neutral{color:#e5e7eb}
.hx-admin-lock{display:flex;align-items:center;justify-content:center;min-height:46vh;padding:18px 0}
.hx-admin-lock-card{width:min(460px,100%);padding:26px 24px;border:1px solid #2c2c30;border-radius:14px;background:#17171a;box-shadow:0 18px 50px rgba(0,0,0,.35)}
.hx-admin-lock-icon{font-size:30px;line-height:1;margin-bottom:10px}
.hx-admin-lock-title{margin:0;font:700 22px/1.2 system-ui;color:#fff}
.hx-admin-lock-sub{margin:7px 0 18px;color:#a1a1aa;font:13px/1.45 system-ui}
.hx-admin-lock-form{display:flex;gap:8px;flex-wrap:wrap}
.hx-admin-password{flex:1 1 220px}
.hx-admin-enter{flex:0 0 auto}
.hx-admin-hint{margin:14px 0 0;color:#8b8b93;font:11px/1.4 system-ui}
.hx-admin-dialog{height:auto!important;max-height:80vh!important;width:min(520px,calc(100vw - 32px))!important}
.hx-admin-dialog-text{margin:0 0 12px;color:#d8d8dc;font:13px/1.5 system-ui;white-space:pre-wrap}
.hx-admin-dialog-warn{margin:0 0 12px;padding:10px 12px;border:1px solid #5a3a12;border-radius:9px;background:#2a1b09;color:#fcd34d;font:12px/1.45 system-ui}
.hx-admin-dialog-field{display:flex;flex-direction:column;gap:6px;margin:0 0 8px;color:#c9ccd1;font:12px system-ui}
.hx-admin-dialog-field .hx-input{width:100%}
.hx-admin-dialog-actions{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px 16px;border-top:1px solid #232327;background:#0b0b0d}
@media (max-width:640px){
  .hx-admin-summary{grid-template-columns:repeat(2,minmax(0,1fr))}
  .hx-admin-row{align-items:flex-start;flex-direction:column}
  .hx-admin-actions{width:100%;justify-content:flex-start}
  .hx-admin-audit-row{grid-template-columns:1fr auto;gap:4px 10px}
  .hx-admin-audit-text{grid-column:1 / -1;white-space:normal}
  .hx-admin-audit-time{grid-column:1 / -1}
}
`;

export function injectStyles() {
  if (document.getElementById('hx-style')) return;
  const style = document.createElement('style');
  style.id = 'hx-style';
  style.textContent = STYLE;
  document.head.appendChild(style);
}
