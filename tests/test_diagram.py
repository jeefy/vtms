
import pytest
from wiring.parser import Wire, Pin, parse_wiring_file
from wiring.diagram import generate_svg, generate_pinouts

@pytest.fixture
def sample_wires():
    """Sample wires for testing."""
    return [
        Wire(color='RED', source=Pin('Fuse Box', '3'), destination=Pin('Start Button', '1'), gauge='18'),
        Wire(color='BLK', source=Pin('Start Button', '2'), destination=Pin('Chassis', 'GND1'), gauge='18'),
        Wire(color='GRN', source=Pin('ECU', '1'), destination=Pin('Coolant Temp Sensor', '1'), gauge='22'),
    ]

def test_generate_svg(tmp_path, sample_wires):
    """Test SVG generation."""
    output_file = tmp_path / "diagram.svg"
    generate_svg(sample_wires, str(output_file))
    
    assert output_file.exists()
    
    content = output_file.read_text()
    assert '<svg' in content
    assert 'Fuse Box' in content
    assert 'Start Button' in content
    assert 'ECU' in content
    assert 'line' in content # a wire should be drawn

def test_generate_pinouts(sample_wires):
    """Test pinout generation."""
    pinouts = generate_pinouts(sample_wires)
    assert "--- Fuse Box ---" in pinouts
    assert "Pin 3: RED to Start Button:1 (18)" in pinouts
    assert "--- Start Button ---" in pinouts
    assert "Pin 1: RED from Fuse Box:3 (18)" in pinouts
    assert "Pin 2: BLK to Chassis:GND1 (18)" in pinouts
    assert "--- ECU ---" in pinouts
    assert "Pin 1: GRN to Coolant Temp Sensor:1 (22)" in pinouts

def test_parser_and_diagram_integration(tmp_path):
    """Test parsing a file and generating diagram and pinouts."""
    wiring_file = tmp_path / "test.wiring"
    wiring_file.write_text("""
# Test wiring
RED "Fuse Box":3 -> "Start Button":1 (gauge=18AWG)
BLK "Start Button":2 -> Chassis:GND1 (gauge=18AWG)
    """)
    
    wires = parse_wiring_file(str(wiring_file))
    assert len(wires) == 2

    # Test SVG
    svg_file = tmp_path / "integrated.svg"
    generate_svg(wires, str(svg_file))
    assert svg_file.exists()
    content = svg_file.read_text()
    assert 'RED' not in content # colors are lowercased for SVG
    assert 'line' in content
    assert 'stroke="red"' in content

    # Test Pinouts
    pinouts = generate_pinouts(wires)
    assert "--- Fuse Box ---" in pinouts
    assert "Pin 3: RED to Start Button:1 (18AWG)" in pinouts

