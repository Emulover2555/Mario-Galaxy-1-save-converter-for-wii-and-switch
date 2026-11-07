Status and limitations

A Switch 1.0.0 save converted to Wii loads correctly in a Wii emulator.
Converting a save to the other platform and back reproduces it byte for byte (for the data both formats store).
Converted blank / early-game slots match real saves from the other platform byte for byte.

Not verified, or known to be lossy

Not tested on real hardware.
Wii → Switch has not been confirmed in-game yet.
Switch-only data has no Wii equivalent and is dropped going to Wii (assist-mode flag, boss-defeated flags and extra counters in the newer layout). Going to Switch these are left at defaults.
A handful of event flags/values use different hash IDs on the two platforms; they are matched by position. This is an inference, not documented behaviour.
The slot "flag" byte (probably crown display) is mapped by an assumption.
Wii 100% saves can contain 121 stars; whether the Switch game accepts that extra star is unknown.

Always back up your saves before using a converted file.

How it works

A GameData.bin is a container (checksum, slot table) holding per-slot blocks of tagged chunks (PLAY, FLG1, PCE1, SPN1, VLE1, GALA, plus config and system blocks). The Wii file is big-endian and the Switch file is little-endian with 4-byte-aligned chunks. The tool decodes each chunk, re-encodes it for the other platform, and recalculates the container checksum.

Credits

Format knowledge comes from the excellent work of ThatNintendoNerd/galaxy_save_data (Rust crates documenting the Galaxy save formats) and from byte-level comparison of real saves. Inspired by timschneeb/galaxy-save-converter. Please check their licenses and credit them if you build on this.

This project is not affiliated with Nintendo. Do not commit commercial game saves you did not create to a public repository.


To use the script, have the gamedata.bin in the directory of python script, open cmd at the directory, and type the following (depending on which conversion you want to do).

python smg1_convert.py switch2wii GameData.bin GameData_wii.bin

Or

python smg1_convert.py wii2switch GameData.bin GameData_switch.bin

You'll need to have python installed and the path variables set for it to work.
