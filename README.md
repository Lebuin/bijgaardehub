This project is designed to be publicly exposed through [Traefik](https://traefik.io/traefik/).


# Installation

* Create a .env file that sets the UID and GID environment variables.
* Run `docker compose up -d`

## VPN services

Home Assistant will need to connect to devices that are not publicly accessible, but are accessible through a VPN. For each of the required VPN connections:

* Create a credentials file `/etc/openvpn/credentials/name` (this file must contain a username and a password, each on its own line)
* Create a profile file `/etc/openvpn/profiles/name.ovpn` which contains the line `auth-user-pass /etc/openvpn/credentials/<name>`
* Create a systemd service based on `example-vpn.service`, replacing the path to the OVPN profile
* Enable the systemd service
