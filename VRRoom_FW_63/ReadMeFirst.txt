
 _    ______  ____                      
| |  / / __ \/ __ \____  ____  ____ ___ 
| | / / /_/ / /_/ / __ \/ __ \/ __ `__ \
| |/ / _, _/ _, _/ /_/ / /_/ / / / / / /
|___/_/ |_/_/ |_|\____/\____/_/ /_/ /_/ 
                                        
Have fun. Please share our work around :)
                                                               
**********\ www.HDfury.com /************





 _     _  _____   ______  ______ _______ ______  _______
 |     | |_____] |  ____ |_____/ |_____| |     \ |______
 |_____| |       |_____| |    \_ |     | |_____/ |______


### HOW TO UPGRADE ###

Please refer to usermanual: www.hdfury.com/docs/HDfuryVRRoom.pdf

We always recommend resetting all settings after each update in case of any issue.
You do it by clicking both checkboxes on RESET area in webserver > config and then type RESET
or you can do it via IP/RS232 with "factoryreset" command. e.g. #vrroom set factoryreset 
or just "set factoryreset" via IP

Please don't forget that you can EXPORT your config BEFORE update and IMPORT it back AFTER update.
This way you won't have to redo any settings.


### Make sure to refresh your browser after update: CTRL + F5 or clear your browser internet cache ### 





 _______ _     _ _______ __   _  ______ _______              _____   ______
 |       |_____| |_____| | \  | |  ____ |______      |      |     | |  ____
 |_____  |     | |     | |  \_| |_____| |______      |_____ |_____| |_____|



########> What's new/fixed in 0.63

- Fixed an EDID mixing error when eARC was the selected item for audio selection in Automix mode.

- Fixed EDID reading issue when user switch from a 4-block TX EDID a 2-block TX EDID.



########> What's new/fixed in 0.62


- Added support for DisplayID 2.0 : 384b (3-blocks) and 512b (4-blocks) EDID in COPY TX mode 

- Added support for DisplayID 2.0 : 384b (3-blocks) and 512b (4-blocks) Custom EDID 1~10

- Added support for DisplayID 2.0 : 384b (3-blocks) and 512b (4-blocks) EDID in AUTOMIX mode

- Added the ability to retain DTD data

- Added support Block Map & HF_EEODB

- Added and fixed some Go232/RS232 commands

- Fixed application restriction issues




########> What's new/fixed in 0.61

- Addressed the problem that the image flashes for a moment when the signal from Kaleidscape source device is repeated

- Additional measures for "Addressed the problem that the signal of the HDMI input path could not be locked when switching the input"

- Supported SBTM (Source-Based Tone Mapping) newly supported by HDMI2.1a standard

- Addressed the problem of flickering when a 480p (FRL) signal is input to a specific TV

- Addressed the problem that VRR with large frame rate changes could not be repeated normally

- Supported Colorimetry [ICtCp, SMPTE2113RGB] newly supported by HDMI2.1a standard

- Addressed the problem that 480p input signal cannot be detected when changing to HDMI repeater after outputting REC656 input 480i signal

- Addressed the problem that the output audio setting may not be set correctly when repeating Audio

- Addressed the problem that HDCP authentication becomes NG when input video signal (HDCP1.4) is upscaled to 8K60_YCC420 

- Addressed the problem that the signal may not be locked if the RxPort is switched after the FRL signal is repeated in the Switch+Repeater configuration

- Added support for reading 3-blocks EDID (Base + CTA_extention + DisplayID_extension)

- Addressed the problem that the TV sometimes flashes when the signal of ChromeCast source device is input

- Addressed the problem that ARC audio stops when the player's audio format of HDMI output is changed to DSD

- Addressed an issue where eARC sound may stop when the cable is unplugged and plugged in

- Addressed the problem that a black screen may appear when re-outputting signals such as when connecting and disconnecting downstream HDMI cable

- Addressed the problem that repeater output does not turn TMDS_ON within 5 seconds when switching to repeater output immediately after signal generator output

- Addressed the problem that downstream HDCP certification may become 1.4 when when the refresh rate of 4K HDR video is switched to 50Hz<->60Hz with Google Chromecast Ultra

- Addressed the problem that downstream HDCP authentication may become 1.4 when the refresh rate is switched to 50Hz<->60Hz in smartphone Google Home application

- Addresses an issue where restarting the HDMI source device may stop outputting audio





########> What's new/fixed in 0.53

- Adjustement in new framework, if it introduces any issue, please revert back to previous version, more update to come.





########> What's new/fixed in 0.51

- New branch of software development with support for newest PCB revisions V1/V2/V3

- Added support for FRL>TMDS downscale on V3 PCB via new OPMODE on webserver > INFO page

- Added LLDV>HDR injection support under VRR signal (still some hiccups on some Samsung TV) 

- Added 2 new eARC and ARC modes, under eARC/ARC selection of webserver > CEC page (set AUTO ARC for ARC TV & AUTO eARC for eARC TV)

- Added DSC detection and routine to disable OSD and prevent Downscale during DSC transmission

- Added OSD for TX1 so it show dowsncaled info separately

- Fixed OSD timing

- Total rewrite of the framework





########> What's new/fixed in 0.34

- OSD Enable unchecked/OFF fixed

- OSD TEXT "never fade" fixed a

- OSD TEXT when clearing the line made issue, fixed as well.




########> What's new/fixed in 0.33


- New MUTE CEC toggle on the WEBSERVER > CEC page for on/off or toggle (for BOSE 900) 

- OSD text now clears when the next string is written (same for the source name)

- Internal changes for the upscaling reporting

- removed the tx0plus5v from webserver and ir/rs232

- OSD ON IP command will activate and now trigger OSD

- Added routine to protect port 80 (cannot be set)

- Fix for iOS APP config read




########> What's new/fixed in 0.30

1. Fixed a few minor refresh and reporting OSD issues



########> What's new/fixed in 0.29

1. Fixed HDR10+ OSD stuck-bug and the HDR+ indicator on OLED/OSD.

2. Added support for CEC mute via eARC OUT and AUDIO OUT. 

Note: CEC mute is not as simple as it sounds. A thing we noticed is that for example Sony TV has a bar that shows the volume level and once it reaches zero there is no more downward volume control possible. 
Since this does not correspond to the Sonos/eARC OUT or the AUDIO OUT volume level in any way at the same time then user have to fix this level so that TV keeps on sending commands. 



########> What's new/fixed in 0.28

1. Added OSD



########> What's new/fixed in 0.27

1. Added reporting for 4096x2160p120 for Nvidia control panel issue

2. Export/import for EDID flags added

3. Earcout5V indicator added on config export to tell if sonos is connected or not (as default SONOS CDS is used since 0.26 to avoid startup/power up sequence issue)

4. Fixed color issue with 420 downscaling (Downscaled TX1 signal displayed with red tint under some conditions)



########> What's new/fixed in 0.26

1. Added a fixed CDS (SONOS Arc) if earc out is selected but eARC device is not active on powerup and fails to issue the CDS properly
in this case (Automix EDID mode) we default to the fixed CDS. Hopefully this helps in issues that ATV doesn't see the proper atmos support on powerup when earc out is selected

2. Added 2 more quick save button to the EDID page, user can now quick save to EDID bank number 8, 9 and 10

3. Added Z9D Custom DV String from the DV string dropdown selector on EDID page




########> What's new/fixed in 0.25

1. Audio out EDID CAPS printed in Webserver > INFO page

2. EDID info reporting adjusted for some displays where it was inaccurate

3. Added X930E LLDV string from Webserver > EDID page > Automix section > DV dropdown

4. Fixed a "no sound" issue from Kodi/Shield and prolly others that was introduced on 0.23

5. Added VSI custom injection




########> What's new/fixed in 0.24

1. Audio improvements

2. ATV channel status fixes

3. eARC speakers maps as new option under CEC page (correction for incorrect marking from TV)

4. Front page change to print where audio comes from

5. earcst/arcst tell which one is active or if neither then HDMI is.

6. internal changes

7. Custom HDR injection automatically OFF if signal is VRR

Note: Reboot needed after firmware flash (or TV power cycle) because TV CEC does not get refreshed unless physical TX0 cable is unplug or unit rebooted.




########> What's new/fixed in 0.23

1. The locktime should be much faster so audio should come out quick

2. Sonos & AVR should now get the proper routing changes and request system audio commands to wakeup and change channel

3. Added another selector for eARC unmute timeout so user can fine tune delays more

4. Some incremental fixes on reporting

5. There was a bug in eARC CDS detection for AVR, fixed.

6. DFHD 1080/1200/1440 detection as well 

7. SINK  EDID 420 / 444 reporting (to know at first sight if input is limited or not on TV)

8. Cosmetics changes asked by users

Note: There is known issue on RS232 commands, will be corrected on FW 0.24



########> What's new/fixed in 0.22

1. Fixed a condition in matrix mode when "copy TX0" or "copy TX1" input port selector option was not retained after switching input

2. Fixed a rare condition at startup when signal could be limited to 4K120 420 8b

3. Improved support for PC GPU when mode change or input switching

4. Added HDCP version reporting on signal info

5. eARC related changes and internal mods

6. Fixed reporting for outgoing bandwidth "0 MHz" 

7. Added "Request Audio Mode" and "Request Audio mode + Routing Change" under CEC page > Audio Out Zone

Note: An AVR needs to be in audio system mode in order to accept volume commands. This is why we cannot just keep a simple power on/off toggle.
"Request Audio Mode" alone should not cause any port changes to the channel we are sending from.
Whereas the second "Request Audio Mode + Routing Change" will change AVR to the port.



########> What's new/fixed in 0.21

1. Added routine for Samsung Q90/QN900/QN95 and similar Samsung models to offer true FRL/VRR/ALLM from Xbox series S/X and FRL/ALLM from PS5

2. Added routine to prevent sound system to turn ON or switch TV input via CEC when system is turned off.



########> What's new/fixed in 0.20

1. Fixed Atmos/DD+ descriptors for Samsung/Sony via ARC

2. Added more setting on the CEC page for AUDIO OUT zone power up/down control. Here you can disable and enable power upping. We will add some more modes later for different types of power up

3. Improved eARC / HDMI switching between sound from TV eARC and sound from HDMI sources at inputs

4. Added the indivudual CEC control for each input port on the CEC page

Note 1 : Added indicator for HDMI / EARC mode but still in progress. Info about it on the OLED page 3 where the RX info is
Note 2 : Default HDCP settings after firmware flash is AUTO, if you import a config exported on previous firmware, please verify HDCP remains set as AUTO after import.



########> What's new/fixed in 0.19

1. Added CEC information on the CEC page

2. Added ARC/eARC TX selector under CEC page (must be set to ARC if ARC sound system is connected at eARC OUT)

2. Added ARC/beam1 and ARC/dd+ option under audio caps in AUTOMIX

4. Added logic around audio out- power up and down

Please note that eARC OUT is now default for AUDIO CAPS under AUTOMIX (you might want to change it to AUDIO OUT if you use AUDIO OUT to your sound system HDMI INPUT).



########> What's new/fixed in 0.18

1. Corrected HDR EDID detection bug in Automix mode that manifested on FW 0.17 (AUTOMIX = COPY TX SINK EDID and MODIFY)

2. Added UNMUTE delay option. Note that it is still under testing, can be set if user hears crackle or pop sound when switching audio format (starting/stopping content/app)



########> What's new/fixed in 0.17

1. Fixed html issues in webserver when monitor edid has specific block (LG 27GP950-B)

2. Fixed config export parameters

3. Added some audio-related reporting fixes


########> What's new/fixed in 0.16

1. Added RS232 commands 


########> What's new/fixed in 0.15

1. Release version 






 ****************************************************
 __  __   ____        ___                             
/\ \/\ \ /\  _`\    /'___\                           
\ \ \_\ \\ \ \/\ \ /\ \__/  __  __   _ __   __  __   
 \ \  _  \\ \ \ \ \\ \ ,__\/\ \/\ \ /\`'__\/\ \/\ \  
  \ \ \ \ \\ \ \_\ \\ \ \_/\ \ \_\ \\ \ \/ \ \ \_\ \ 
   \ \_\ \_\\ \____/ \ \_\  \ \____/ \ \_\  \/`____ \
    \/_/\/_/ \/___/   \/_/   \/___/   \/_/   `/___/> \
                                                /\___/
                                                \/__/
*****************\ www.HDfury.com /*******************


Need a discount code ? Share a link to us, write a review, 
tell people on any forum how cool we are and you will be rewarded with discount code!
the more you do, bigger will be the discount, do something amazing and get a FREE HDFURY!

