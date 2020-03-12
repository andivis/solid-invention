# marketplaces

## Video

https://www.loom.com/share/a066de46befb49eebd3edadd59ea0bf2

https://www.loom.com/share/9e5e0760ebc34be8acba547a4defd5a9

## Installation

1. If you don't have it already, install git from https://git-scm.com/downloads
2. Open a command prompt window
3. Type `cd (directory where you want to put the app)` and press enter
4. Run the command below in a command prompt.

`git clone https://github.com/andivis/solid-invention.git`

## Instructions

1. Open `directory where you want to put the app`
2. Open the file called `input.csv` in a spreadsheet program or text editor. Edit the file as needed.
    1. The `craigslist ad must contain a picture` can be set to `true`. If so, require a picture. Blank or any other value means don't require a picture.
    2. The `craigslist ad must contain` is a semi-colon separated list of phrases. At least one of those phrases must appear in the Craigslist ad.
    3. The `craigslist ad must not contain` is a semi-colon separated list of phrases to avoid. If at least one of those phrases appears in the Craigslist ad, it skips that ad.
3. Double click `marketplaces.bat`. It'll write a link to itself in `C:\Users\(your username)\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`. This allows the app to launch on system startup.
5. Optionally, double click `show-hide-window.bat` to hide/show the command prompt window

## Options

`options.ini` accepts the following options:

- `emailProvider`: What service to send emails with. Can be `sendgrid` or `gmail`. Default: `sendgrid`.
- `fromEmailAddress`: What will appear in the "From" field in the emails this app sends.
- `toEmailAddress`: Where to send the notification emails. Default: (blank).