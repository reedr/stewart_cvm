"""Stewart CVM Device."""

import asyncio
import logging
import re

from homeassistant.core import HomeAssistant, callback

from .const import CVM_CONNECT_TIMEOUT, CVM_LOGIN_TIMEOUT, CVM_PORT

_LOGGER = logging.getLogger(__name__)

MIN_COVER_POSITION = 0
MAX_COVER_POSITION = 100

class CVMDevice:
    """Represents a single CVM device."""

    def __init__(
        self, hass: HomeAssistant, host: str, username: str, password: str, presets: str, maxpos: str
    ) -> None:
        """Set up class."""

        self._hass = hass
        self._host = host
        self._username = username
        self._password = password
        self._presets = [float(ar) for ar in presets.split(",")]
        self._min_aspect = min(self._presets)
        self._max_aspect = max(self._presets)
        self._max_raw_position = float(maxpos)
        self._device_id = f"CVM:{host}"
        self._reader: asyncio.StreamReader
        self._writer: asyncio.StreamWriter
        self._online = False
        self._callback = None
        pat = r'[^!#]*([!#])1\.1\.(\d)\.MOTOR(\.[^=]+)?=([?.0-9A-Z]+)'
        self._match_re = re.compile(pat.encode('ascii'))
        self._data = {"position": None, "motor_status": "STOP", "motor_position": None, "aspect_ratio": None, "screen_preset": None,
                      "preset_aspects": presets, "preset_positions": [self.aspect_to_position(ar) for ar in self._presets]}
        self._init_event = asyncio.Event()
        self._listener = None
        _LOGGER.debug("setup: host=%s presets=%s maxpos=%.2f", self._host, self._presets, self._max_raw_position)

    @property
    def device_id(self) -> str:
        """Use the mac."""
        return self._device_id

    @property
    def online(self) -> bool:
        """Return status."""
        return self._online

    @property
    def data(self) -> dict:
        """Dev data."""
        return self._data

    def position_to_aspect(self, position: int) -> float:
        """Convert cover position to aspect ratio."""
        aspect: float
        if position == 0:
            aspect = self._min_aspect
        elif position == 100:
            aspect = self._max_aspect
        else:
            aspect = ((float(position) / MAX_COVER_POSITION) * (self._max_aspect - self._min_aspect)) + self._min_aspect
        return aspect

    def aspect_to_position(self, aspect: float) -> int:
        """Convert aspect ratio to cover position."""
        x1 = aspect - self._min_aspect
        x2 = x1 / (self._max_aspect - self._min_aspect)
        x3 = max(min(int(x2 * MAX_COVER_POSITION), 100), 0)
        return x3  # noqa: RET504

    def raw_position_to_position(self, raw_position: float) -> int:
        """Convert raw motor position to cover position."""
        x1 = raw_position / self._max_raw_position
        x2 = x1 * MAX_COVER_POSITION
        x3 = min(int(x2), MAX_COVER_POSITION)
        x4 = MAX_COVER_POSITION - x3
        # _LOGGER.debug("%.2f %.2f %d %d", x1, x2, x3, x4)
        return x4  # noqa: RET504

    def position_lookup(self, position: int) -> tuple[float, int]:
        """Return the narrowest preset that fits."""
        aspect = self.position_to_aspect(position)
        low_aspect = 1000.0
        low_preset = 0
        for i, pa in enumerate(self._presets):
            # _LOGGER.debug("%.2f ?< %.2f ?< %.2f", aspect, pa, low_aspect)
            if aspect <= pa < low_aspect:
                low_aspect = self._presets[i]
                low_preset = i+1
        return (low_aspect, low_preset)

    async def open_connection(self, test: bool=False) -> bool:
        """Establish a connection."""
        if self.online:
            return True

        try:
            _LOGGER.debug("Establish new connection")
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, CVM_PORT),
                timeout=CVM_CONNECT_TIMEOUT
            )
            await asyncio.wait_for(
                self._reader.readuntil(b"User:"),
                timeout=CVM_LOGIN_TIMEOUT
            )
            self._writer.write(self._username.encode('ascii') + b"\r")
            await asyncio.wait_for(
                self._reader.readuntil(b"Password:"),
                timeout=CVM_LOGIN_TIMEOUT
            )
            self._writer.write(self._password.encode('ascii') + b"\r")
            await asyncio.wait_for(
                self._reader.readuntil(b"Connected:"),
                timeout=CVM_LOGIN_TIMEOUT
            )
            if test:
                self._writer.close()
            else:
                self._online = True
                self._listener = asyncio.create_task(self.listener())

        except (TimeoutError, OSError) as err:
            self._online = False
            _LOGGER.error("Connect sequence error %s", err)
            raise ConnectionError("Connect sequence error") from err

        return True

    async def test_connection(self) -> bool:
        """Test a connect."""
        return await self.open_connection(test=True)

    async def send_command(self, command: str) -> bool:
        """Make an API call."""
        if await self.open_connection():
            cmd = command.encode('ascii') + b"\r\n"
            _LOGGER.debug("-> %s", str(cmd))
            self._writer.write(cmd)
            return True
        return False

    async def send_query_position(self) -> bool:
        """Query."""
        return await self.send_command("#1.1.1.MOTOR.POSITION=?")

    async def send_recall(self, preset: int) -> bool:
        """Recall a preset."""
        return await self.send_command(f"#1.1.0.MOTOR=RECALL,{preset};")

    async def set_position(self, position: int) -> bool:
        """Setit."""
        (aspect, preset) = self.position_lookup(position)
        return await self.send_recall(preset)

    async def open_mask(self) -> bool:
        """Open wide."""
        return await self.send_command("#1.1.0.MOTOR=RETRACT;")

    async def close_mask(self) -> bool:
        """Narrow bridge."""
        return await self.send_recall(self.get_preset(0))

    async def stop_mask(self) -> bool:
        """Stop moving."""
        return await self.send_command("#1.1.0.MOTOR=STOP;")

    async def async_init(self, data_callback: callback) -> dict:
        """Query position and wait for response."""
        self._callback = data_callback
        await self.send_query_position()
        await asyncio.wait_for(
            self._init_event.wait(),
            timeout=CVM_LOGIN_TIMEOUT
        )
        return self._data

    async def listener(self) -> None:
        """Listen for status updates from device."""

        while True:
            try:
                line = await self._reader.readuntil(b"\r")
                _LOGGER.debug("<- %s", str(line))

                match = self._match_re.match(line)
#                _LOGGER.error(str(match.group(1, 2, 3, 4)))
                if match is None:
                    _LOGGER.error("Unexpected screen response: %s", line)
                elif match.group(1) == b"!" and match.group(2) == b"1":
                    if match.group(3) == b".POSITION":
                        raw_position = float(match.group(4))
                        position = self.raw_position_to_position(raw_position + 1.0)
                        if position != self._data["position"]:
                            (aspect, preset) = self.position_lookup(position)
                            _LOGGER.debug("Mask position: motor=%.2f position=%d aspect=%.2f preset=%d", raw_position, position, aspect, preset)
                            self._data["position"] = position
                            self._data["motor_position"] = raw_position
                            self._data["aspect_ratio"] = aspect
                            self._data["screen_preset"] = preset
                            if not self._init_event.is_set():
                                self._init_event.set()
                            if self._callback is not None:
                                self._callback(self._data)
                    elif match.group(3) == b".STATUS":
                        status = str(match.group(4), encoding='ascii')
                        if status != self._data["status"]:
                            _LOGGER.debug("Mask status: %s", status)
                            self._data["status"] = status
                            if self._callback is not None:
                                self._callback(self._data)

            except (asyncio.IncompleteReadError) as err:
                _LOGGER.error("Connection lost: %s", err)
                self._writer.close()
                self._online = False
                break
