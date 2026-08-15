# NVR RPC API map — DHI-NVR5232-4KS2, FW 4.002.0000000.8.R (2024-10-30)
# Web3.0 H5 RPC2. Session carried in JSON body top-level "session" (NOT cookie).
# Read-only probe results, 2026-08. Scripts: rpc_probe.py / rpc_channels.py / rpc_network.py

## Identity (magicBox.*) — all OK
- magicBox.getProductDefinition  params: {"name":"<Feature>"} — features: VideoAnalyse, RemoteVideoAnalyse,
  HasTalk, HasAlarm, HasAudio, HasPtz... unknown names -> error 268959743
- magicBox.getDeviceType -> DHI-NVR5232-4KS2
- magicBox.getHardwareVersion -> V1.0
- magicBox.getSoftwareVersion -> {"Version":"4.002.0000000.8.R","BuildDate":"2024-10-30","WebVersion":"3.2.7.147280","SecurityBaseLineVersion":"V2.2"}
- magicBox.getSerialNo -> 8B02C47PAZ58EDD
- magicBox.getMachineName -> NVR-BORNA RAD
- magicBox.getSystemInfo -> {serialNumber, deviceType:"31", processor:"ST7108", updateSerial}
- magicBox.getVendor -> Dahua ; getDeviceClass -> NVR
- NOT on this FW: getMAC, getDeviceModel, getDeviceFamily, getLanguage, getCurrentTime,
  getLocalTime, getTimeZone, getLoginType, getRemoteDeviceNumber, getLocalZone (268894210)

## configManager.getConfig {"name": "<Table>", "onlyLocal": false}
OK tables: Network, General, Record, RecordMode, Alarm, ChannelTitle, RemoteDevice,
  RemoteDeviceLimitList, Stream(Encode), Email, AutoMaintain, DDNS, PPPoE, NAT, Multicast,
  Time, SyncLocalityConfig, AutoAddRemoteDevice, AlarmOut, MediaEncrypt, Holiday, MotionDetect
DENIED (285278249 "Authority:check failure." — account lacks privilege): VideoEncode, Snapshot,
  Storage, PTZ, VideoAnalyze, User, Security, SSL, FTP, NFS, ISCSI, HDDManage, Upgrade,
  CloudUpgrade, IPFilter, Route, GbE, etc. NOTE: admin account would get these.

## Channels / cameras
- LogicDeviceManager.getCameraState {"uniqueChannels":[-1]} -> 32 entries {channel, connectionState: Connected|Unconnect|Empty}
- LogicDeviceManager.getCameraLoginErrorCode {"channel":N} -> errorCode (268632082/84 = ok-ish, 268632100 = channel issue)
- LogicDeviceManager.getVideoChannelsInfo {"type":"Input"} -> null here (shape quirk)
- VideoLink.getAllLinkChannels {} -> linkList (null when no linking)
- ChannelTitle table -> 32 names; this site: FRONT_L/R, F0_CAM1..4, ASANSOR, F5..F1 pairs,
  F-1_NAMAZ/RESTORAN/STOR1-4, ROOF_*, REAR_*, F0_SEC
- configManager.getConfig RemoteDevice -> uuid:System_CONFIG_NETCAMERA_INFO_N entries:
  {Name(SN), Enable, Address, Mac, Port:37777, HttpPort:80, HttpsPort:443, UserName:"admin",
   Password:"******", Vendor:"Private", ProtocolType:"Private", DeviceType}
  31 cams on 192.168.40.2-35 (ch30 = 192.168.40.225); all Dahua, admin creds stored.
- POS.getAll -> pos list (8 POS overlays configured, all Enable:false)

## Media file search (playback) — read-only, must close
- mediaFileFind.factory.create {} -> instance (null)
- mediaFileFind.findFile {"condition":{"Channel":N,"StartTime":"YYYY-MM-DD HH:mm:ss",
  "EndTime":"...","Types":["dav"],"VideoStream":"Main","Events":["*"],"Flags":null}}
- mediaFileFind.findNextFile {"count":1024}
- mediaFileFind.close / mediaFileFind.destroy

## Misc (read-only)
- CloudUpgrader.getAutoCheck -> {"flag":false}
- pwdAgent.getPreSecret -> {"status":1}
- workDirectory.factory.instance {"name":"/"} + workDirectory.getBitmapEx
  {"condition":{"Channel":-1,"Events":["*"],"Month":8,"Year":2026,"Types":[]}}
- RemoteDeviceManager.factory.instance + getCaps (getCaps errored -267976703 standalone)
- ptz.factory.instance {"channel":N} + ptz.getCurrentProtocolCaps (needs instance context;
  standalone errored -267976703); ptz.factory.destroy denied for this account
- deviceDiscovery.factory.instance / attach {"proc":1|2} / start {"timeout":15} / stop — scans LAN
- userManager.getAuthorityList -> 77 auth names; getCaps -> pwd policy; getUserList NOT on FW

## Keep-alive / session
- global.keepAlive {"timeout":300,"active":true} — browser sends every ~5min; server answers {"timeout":60}
- Session expires if not kept alive; token bound to client IP.

## Observed UI write calls during user navigation (capture 2026-08-13)
- configManager.setConfig {"name":"SyncLocalityConfig","table":{"H265Enable":true,"LanguageEnable":true,"TimeZoneEnable":true,"VideoStandardEnable":true}}
- configManager.setConfig {"name":"AutoAddRemoteDevice","table":{"Enable":true}}
These were emitted by the web UI itself while browsing — the page writes some tables on load.
