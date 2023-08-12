def getFloat(value):
    """Read value and returns a float. If error return NaN."""
    if value:
        try:
            return float(value)
        except ValueError:
            return float('NaN')
    return value

def getInt(value):
    """Read value and returns a int. If error return None."""
    try:
        return int(value)
    except ValueError:
        return None
    
def cleanLine(line: str):
    """Clean line of semicolon and comments."""
    return line.split(";")[0].strip()

def read_prop_single(line: str):
    """Read and return a property of single value: (prop, value)"""
    
    line = cleanLine(line)
    prop = line.split()[0]
    value = line.split()[1]

    return prop, value

def read_prop_anim(line: str):
    """Read anim line in one of 2 possible forms. Returns prop list."""

    line = cleanLine(line)
    offset = len("anim ")
    props = line[offset:].split()
    isEmpty = False
    if len(props) < 4:
        isEmpty = True

    # cast last 3 elements to int
    for i in range(-3, 0):
        props[i] = getInt(props[i])

    return props, isEmpty

def read_prop_keyframe(line: str):
    """Read single keyframe properties.\n
    The amount of returned props can vary depending on in and out tangent types.
    For each 'fixed' tangent, two floats are added for angle and weight."""

    line = cleanLine(line)
    props = line.split()
    
    # first 2 elements are float, next 2 are strings, next 3 are integers and last 2 or 4 are float (animVersion >= 1.1 only)
    for i, p in enumerate(props):
        if i <= 1 or i >= 7:
            props[i] = getFloat(props[i])
        elif i >= 4 and i <= 6:
            props[i] = bool(getInt(props[i]))

    return props
