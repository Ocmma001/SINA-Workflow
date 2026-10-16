import unittest
from modules.text_binding import assign_text, analyze_text_bindings


def text(value, x, y):
    return {'text':value,'confidence':.9,'bbox':[[x-2,y-2],[x+2,y-2],[x+2,y+2],[x-2,y+2]]}


class TextBindingTests(unittest.TestCase):
    def test_far_note_is_not_forced_onto_nearest_symbol(self):
        data={'components':[{'id':'R1','type':'Resistor','bbox':[0,0,10,10]}],'ocr':[text('100',100,100)]}
        self.assertEqual(assign_text(data)['R1'],[])

    def test_tie_between_components_stays_ambiguous(self):
        data={'components':[{'id':'R1','type':'Resistor','bbox':[0,0,10,10]},
                            {'id':'R2','type':'Resistor','bbox':[20,0,30,10]}],'ocr':[text('10k',15,5)]}
        result=analyze_text_bindings(data)
        self.assertEqual(result['diagnostics'][0]['status'],'ambiguous')
        self.assertFalse(any(result['assignments'].values()))

    def test_ref_type_and_units_constrain_assignment(self):
        components=[{'id':'R','type':'Resistor','bbox':[0,0,10,10]},
                    {'id':'V','type':'Voltage_src','bbox':[20,0,30,10]}]
        data={'components':components,'ocr':[text('5 V',11,5),text('R1',18,5)]}
        assigned=assign_text(data)
        self.assertEqual([t['text'] for t in assigned['V']],['5 V'])
        self.assertEqual([t['text'] for t in assigned['R']],['R1'])

    def test_invalid_coordinates_and_unsupported_symbols_are_skipped(self):
        data={'components':[{'id':'G','type':'GND','bbox':[0,0,10,10]}],
              'ocr':[text('R1',5,5),{'text':'1','bbox':[0,0,float('nan'),10]}]}
        result=analyze_text_bindings(data)
        self.assertFalse(any(result['assignments'].values()))
        self.assertEqual(result['diagnostics'][1]['status'],'invalid_box')


    def test_low_confidence_numeric_noise_is_not_adopted(self):
        noise=text('3',5,5)
        noise['confidence']=.21
        data={'components':[{'id':'R','type':'Resistor','bbox':[0,0,10,10]}],'ocr':[noise]}
        self.assertEqual(analyze_text_bindings(data)['diagnostics'][0]['status'],'low_confidence')
        self.assertEqual(assign_text(data)['R'],[])

    def test_bare_number_does_not_move_from_transistor_to_resistor(self):
        data={'components':[{'id':'Q','type':'Transistor_BJT','bbox':[0,0,10,10]},
                            {'id':'R','type':'Resistor','bbox':[20,0,30,10]}],'ocr':[text('3',11,5)]}
        result=assign_text(data)
        self.assertEqual(len(result['Q']),1)
        self.assertEqual(result['R'],[])
