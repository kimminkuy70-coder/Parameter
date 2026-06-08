from collections import OrderedDict


def parse_ini_file(filepath):
    """
    INI 파일 파싱

    Returns:
        {
            'sections_order': ['[General]', '[GenesisV12]', ...],
            'data': {
                '[General]': OrderedDict([('ZoneName', '2um'), ...]),
                ...
            }
        }
    """
    sections_order = []
    data = OrderedDict()
    current_section = None

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                current_section = line
                if current_section not in data:
                    sections_order.append(current_section)
                    data[current_section] = OrderedDict()
            elif '=' in line and current_section is not None:
                key, _, value = line.partition('=')
                data[current_section][key.strip()] = value.strip()

    return {'sections_order': sections_order, 'data': data}
