"""Portable storage fixtures only; no native payload or garment admission."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

from a3d import native_diagnostic_arrays as codec
from a3d.core import StudioError


class PortableVector:
    def __init__(self,values):self.values=list(values)
    def __len__(self):return len(self.values)
    def __getitem__(self,index):return self.values[index]


class Float32Vector(PortableVector):
    def __init__(self,values):super().__init__([struct.unpack('<f',struct.pack('<f',v))[0]for v in values])


def budget(**kwargs):return codec.CodecBudget(check=kwargs.pop('check',lambda phase:None),**kwargs)


def bits(value):return struct.pack('<d',value)


def v3(value):
    """Independent small legacy storage oracle, never the native serializer."""
    if type(value)is PortableVector or type(value)is Float32Vector:
        return {'native_type':'mathutils.Vector','values':[v3(value[i])for i in range(len(value))]}
    if type(value)is tuple:return {'native_sequence_type':'TUPLE','values':[v3(v)for v in value]}
    if type(value)is list:return [v3(v)for v in value]
    if type(value)is dict:
        if value and all(type(k)is int for k in value):
            return {'native_mapping_type':'INTEGER_KEYS','entries':[[k,v3(value[k])]for k in sorted(value)]}
        return {k:v3(v)for k,v in value.items()}
    return value


def nodes(value):
    if type(value)is dict:return 1+len(value)+sum(nodes(v)for v in value.values())
    if type(value)is list:return 1+sum(nodes(v)for v in value)
    return 1


def dump(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')


def encoded_dump(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('utf-8')


def reseal(packet):
    packet['receipt']['output_nodes']=nodes(packet)
    for _ in range(10):
        size=len(encoded_dump(packet))+1
        if packet['receipt']['output_bytes']==size:return encoded_dump(packet)+b'\n'
        packet['receipt']['output_bytes']=size
    raise AssertionError('Fixture size did not settle')


class NativeDiagnosticArraysTests(unittest.TestCase):
    def refuse(self,reason,call):
        with self.assertRaises(StudioError)as caught:call()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.qualification,'NONE')
        return caught.exception

    def exact(self,expected,actual,canonical_int=True):
        self.assertIs(type(expected),type(actual))
        if type(expected)is float:self.assertEqual(bits(expected),bits(actual))
        elif type(expected)is dict:
            keys=sorted(expected)if canonical_int and expected and all(type(k)is int for k in expected)else list(expected)
            self.assertEqual(keys,list(actual))
            for k in keys:self.exact(expected[k],actual[k],canonical_int)
        elif type(expected)in(list,tuple,PortableVector,Float32Vector):
            self.assertEqual(len(expected),len(actual))
            for i in range(len(expected)):self.exact(expected[i],actual[i],canonical_int)
        else:self.assertEqual(expected,actual)

    def roundtrip(self,value,vector_type=None):
        before=copy.deepcopy(value);b=budget()
        raw=codec.pack_native_diagnostic_arrays(value,budget=b,vector_type=vector_type)
        packet=json.loads(raw)
        self.assertEqual(packet['receipt']['output_nodes'],nodes(packet))
        self.assertEqual(packet['receipt']['output_bytes'],len(raw))
        self.assertEqual(b.usage['nodes'],nodes(packet));self.assertEqual(b.usage['bytes'],len(raw))
        read=budget();result=codec.unpack_native_diagnostic_arrays(raw,budget=read,vector_type=vector_type)
        self.exact(value,result);self.exact(before,value,canonical_int=False)
        self.assertEqual(read.usage['nodes'],nodes(v3(value)))
        self.assertEqual(read.usage['bytes'],len(dump(v3(value))))
        return packet,raw

    def test_binary64_signedzero_and_adjacent_exact(self):
        values=[-0.,0.,math.nextafter(1.,0.),1.,math.nextafter(1.,math.inf),-1.,1e-300,1e300]
        packet,_=self.roundtrip(values)
        self.assertEqual(packet['payload']['dtype'],'BINARY64_LE')
        raw=base64.b64decode(packet['payload']['data'])
        self.assertEqual(raw,b''.join(bits(v)for v in values))

    def test_int64_limits_exact(self):
        packet,_=self.roundtrip([-(1<<63),(1<<63)-1,0,-1,1,2,3,4])
        self.assertEqual(packet['payload']['dtype'],'INT64_LE')

    def test_list_tuple_matrix_containers(self):
        for outer in(list,tuple):
            for row in(list,tuple):
                with self.subTest(outer=outer,row=row):
                    packet,_=self.roundtrip(outer(row([float(i),-0.])for i in range(4)))
                    self.assertEqual(packet['payload']['shape'],[4,2])
                    self.assertEqual(packet['payload']['container'],outer.__name__.upper())
                    self.assertEqual(packet['payload']['row_container'],row.__name__.upper())

    def test_integer_map_numeric_canonical_order(self):
        packet,_=self.roundtrip({9:0,-4:7,5:-8,0:2})
        self.assertEqual(packet['payload']['tag'],'INT_MAP_ARRAY')
        self.assertEqual(list(struct.unpack('<8q',base64.b64decode(packet['payload']['data']))),[-4,7,0,2,5,-8,9,0])

    def test_vector_adapter_explicit(self):
        packet,_=self.roundtrip(tuple(PortableVector([float(i),-0.])for i in range(4)),PortableVector)
        self.assertEqual(packet['payload']['row_container'],'VECTOR')
        self.roundtrip(PortableVector([1.,-0.,math.nextafter(1.,math.inf)]),PortableVector)

    def test_float32_adapter_representable_only(self):
        self.roundtrip([Float32Vector([float(i),-0.])for i in range(4)],Float32Vector)
        raw=codec.pack_native_diagnostic_arrays([PortableVector([math.nextafter(1.,math.inf),0.])for _ in range(4)],budget=budget(),vector_type=PortableVector)
        self.refuse('VECTOR_ROUNDTRIP',lambda:codec.unpack_native_diagnostic_arrays(raw,budget=budget(),vector_type=Float32Vector))

    def test_small_mixed_bool_and_wide_integer_fallback(self):
        for value in([1,2,3],[True]*8,[1.,2,False,'x',None],list(range(7))+[1<<80],{1<<90:4,0:5}):
            with self.subTest(value=value):
                packet,_=self.roundtrip(value)
                self.assertNotIn(packet['payload']['tag'],('ARRAY','INT_MAP_ARRAY'))

    def test_strings_and_reports_not_suppressed(self):
        value={'r1':{'data':[0.]*8,'name':'é\n\u0001😀'},'r2':{'data':[0.]*8,'name':'é\n\u0001😀'},'empty':{},'t':()}
        packet,_=self.roundtrip(value)
        self.assertEqual([row[0]for row in packet['payload']['entries']],list(value))
        self.assertEqual(len(packet['payload']['entries']),4)

    def test_source_tag_collision_encapsulated(self):
        value={'tag':'ARRAY','dtype':'BINARY64_LE','shape':[8],'data':'x','discriminant':codec.DISCRIMINANT}
        packet,_=self.roundtrip(value)
        self.assertEqual(packet['payload']['tag'],'MAP')

    def test_empty_scalar_and_ragged(self):
        for value in(None,False,-0.,1<<100,'\t"\\é',[],(),{},[[],[1,2]],[[1,2],[3,4,5]]):
            with self.subTest(value=value):self.roundtrip(value)

    def test_no_array_when_row_types_differ(self):
        packet,_=self.roundtrip([(1.,2.),[3.,4.],(5.,6.),[7.,8.]])
        self.assertEqual(packet['payload']['tag'],'LIST')

    def test_closed_types_keys_nonfinite_and_cycles(self):
        class SubList(list):pass
        for value,reason in((SubList([1]),'UNSUPPORTED_TYPE'),({True:1},'AMBIGUOUS_KEYS'),({'x':1,0:2},'AMBIGUOUS_KEYS'),(float('inf'),'NONFINITE'),('\ud800','INVALID_STRING'),(b'x','UNSUPPORTED_TYPE')):
            self.refuse(reason,lambda value=value:codec.pack_native_diagnostic_arrays(value,budget=budget()))
        value=[];value.append(value)
        self.refuse('CYCLE',lambda:codec.pack_native_diagnostic_arrays(value,budget=budget()))

    def test_vectors_not_implicitly_supported(self):
        self.refuse('UNSUPPORTED_TYPE',lambda:codec.pack_native_diagnostic_arrays(PortableVector([1.,2.]),budget=budget()))
        self.refuse('INVALID_VECTOR_TYPE',lambda:codec.pack_native_diagnostic_arrays([],budget=budget(),vector_type=list))
        self.refuse('UNSUPPORTED_VECTOR',lambda:codec.pack_native_diagnostic_arrays(PortableVector([1,2]),budget=budget(),vector_type=PortableVector))
        raw=codec.pack_native_diagnostic_arrays(PortableVector([1.,2.]),budget=budget(),vector_type=PortableVector)
        self.refuse('UNSUPPORTED_VECTOR',lambda:codec.unpack_native_diagnostic_arrays(raw,budget=budget()))

    def test_packet_metadata_closed(self):
        _,raw=self.roundtrip(list(range(8)));packet=json.loads(raw)
        for key,value in(('version',True),('qualification','PASS'),('codec_sha256','0'*64),('extra',1)):
            altered=copy.deepcopy(packet);altered[key]=value
            self.refuse('INVALID_DTO',lambda altered=altered:codec.unpack_native_diagnostic_arrays(reseal(altered),budget=budget()))

    def test_receipt_binding_and_fields(self):
        _,raw=self.roundtrip(list(range(8)));packet=json.loads(raw)
        for field in('output_nodes','output_bytes'):
            altered=copy.deepcopy(packet);altered['receipt'][field]+=1
            self.refuse('INVALID_RECEIPT',lambda altered=altered:codec.unpack_native_diagnostic_arrays(dump(altered)+b'\n',budget=budget()))
        altered=copy.deepcopy(packet);altered['receipt']['scope']='NATIVE_LEDGER'
        self.refuse('INVALID_RECEIPT',lambda:codec.unpack_native_diagnostic_arrays(reseal(altered),budget=budget()))

    def test_shapes_dtypes_and_extra_fields(self):
        _,raw=self.roundtrip(list(range(8)));packet=json.loads(raw)
        for field,value,reason in(('shape',[True],'INVALID_SHAPE'),('shape',[8,0],'INVALID_SHAPE'),('shape',[8,1,1],'INVALID_SHAPE'),('dtype','FLOAT32','INVALID_DTYPE'),('dtype',[],'INVALID_DTYPE'),('container',[],'INVALID_CONTAINER'),('row_container','LIST','INVALID_CONTAINER'),('extra',1,'INVALID_TAG')):
            with self.subTest(field=field,value=value):
                altered=copy.deepcopy(packet);altered['payload'][field]=value
                self.refuse(reason,lambda altered=altered:codec.unpack_native_diagnostic_arrays(reseal(altered),budget=budget()))

    def test_base64_length_alphabet_and_canonical_padding(self):
        _,raw=self.roundtrip(list(range(8)));packet=json.loads(raw)
        original=packet['payload']['data']
        for data in(original[:-1],original[:-2]+'!?',original[:-3]+'B=='):
            altered=copy.deepcopy(packet);altered['payload']['data']=data
            self.refuse('INVALID_BASE64',lambda altered=altered:codec.unpack_native_diagnostic_arrays(reseal(altered),budget=budget()))

    def test_binary_nonfinite_refused(self):
        _,raw=self.roundtrip([0.]*8);packet=json.loads(raw)
        packet['payload']['data']=base64.b64encode(struct.pack('<8d',float('nan'),*([0.]*7))).decode('ascii')
        self.refuse('NONFINITE',lambda:codec.unpack_native_diagnostic_arrays(reseal(packet),budget=budget()))

    def test_intmap_unsorted_and_duplicate(self):
        _,raw=self.roundtrip({i:i for i in range(4)});packet=json.loads(raw)
        for keys in([0,0,2,3],[0,2,1,3]):
            altered=copy.deepcopy(packet);cells=[x for k in keys for x in(k,k)]
            altered['payload']['data']=base64.b64encode(struct.pack('<8q',*cells)).decode('ascii')
            self.refuse('INVALID_MAP',lambda altered=altered:codec.unpack_native_diagnostic_arrays(reseal(altered),budget=budget()))

    def test_fallback_map_ambiguity_and_order(self):
        _,raw=self.roundtrip({0:False,1:False});packet=json.loads(raw)
        for entries in([[0,False],[0,True]],[[1,False],[0,False]],[[True,False],[1,False]]):
            altered=copy.deepcopy(packet);altered['payload']['entries']=entries
            self.refuse('INVALID_MAP',lambda altered=altered:codec.unpack_native_diagnostic_arrays(reseal(altered),budget=budget()))

    def test_invalid_json_duplicate_nonfinite_and_lf(self):
        for raw,reason in((b'{"x":0,"x":1}\n','DUPLICATE_KEY'),(b'NaN\n','NONFINITE'),(b'1e999\n','NONFINITE'),(b'{}','INVALID_DTO'),(b'{}\r\n','INVALID_DTO'),(b'\xff\n','INVALID_DTO')):
            self.refuse(reason,lambda raw=raw:codec.unpack_native_diagnostic_arrays(raw,budget=budget()))

    def test_output_exact_cap_and_cap_minus_one(self):
        raw=codec.pack_native_diagnostic_arrays(list(range(20)),budget=budget());n=nodes(json.loads(raw))
        self.assertEqual(codec.pack_native_diagnostic_arrays(list(range(20)),budget=budget(limits={'max_nodes':n,'max_bytes':len(raw)})),raw)
        error=self.refuse('NODES',lambda:codec.pack_native_diagnostic_arrays(list(range(20)),budget=budget(limits={'max_nodes':n-1})))
        self.assertEqual((error.used,error.requested,error.limit),(0,n,n-1))
        self.refuse('BYTES',lambda:codec.pack_native_diagnostic_arrays(list(range(20)),budget=budget(limits={'max_bytes':len(raw)-1})))

    def test_global_initial_usage_and_two_outputs(self):
        raw=codec.pack_native_diagnostic_arrays([0.]*8,budget=budget());n=nodes(json.loads(raw))
        b=budget(limits={'max_nodes':n*2,'max_bytes':len(raw)*2},usage={'nodes':n,'bytes':len(raw)})
        self.assertEqual(codec.pack_native_diagnostic_arrays([0.]*8,budget=b),raw)
        self.assertEqual(b.usage['nodes'],n*2)
        self.refuse('NODES',lambda:codec.pack_native_diagnostic_arrays([0.]*8,budget=b))
        self.assertEqual(b.usage['nodes'],n*2)

    def test_expansion_quota_before_base64_allocation(self):
        raw=codec.pack_native_diagnostic_arrays(list(range(1000)),budget=budget());phases=[]
        error=self.refuse('NODES',lambda:codec.unpack_native_diagnostic_arrays(raw,budget=budget(check=phases.append,limits={'max_nodes':1000})))
        self.assertEqual(error.requested,1001)
        self.assertNotIn('codec_before_base64_decode',phases)

    def test_decode_cost_exact_expanded_v3(self):
        value={0:(1.,2.),1:(3.,4.)};raw=codec.pack_native_diagnostic_arrays(value,budget=budget())
        expected=v3(value);n=nodes(expected);size=len(dump(expected))
        self.exact(value,codec.unpack_native_diagnostic_arrays(raw,budget=budget(limits={'max_nodes':n,'max_bytes':size})))
        self.refuse('NODES',lambda:codec.unpack_native_diagnostic_arrays(raw,budget=budget(limits={'max_nodes':n-1})))
        self.refuse('BYTES',lambda:codec.unpack_native_diagnostic_arrays(raw,budget=budget(limits={'max_bytes':size-1})))

    def test_same_ledger_encode_decode_no_free_output(self):
        value=list(range(8));b=budget();raw=codec.pack_native_diagnostic_arrays(value,budget=b);first=b.usage
        self.exact(value,codec.unpack_native_diagnostic_arrays(raw,budget=b))
        self.assertEqual(b.usage['nodes'],first['nodes']+9)
        self.assertEqual(b.usage['bytes'],first['bytes']+len(dump(value)))

    def test_depth_distinguished_and_bounded_diagnostic(self):
        value=[]
        for _ in range(20):value=[value]
        error=self.refuse('DEPTH',lambda:codec.pack_native_diagnostic_arrays(value,budget=budget(limits={'max_depth':14})))
        self.assertEqual(error.observed_depth,15);self.assertEqual(len(error.path),12);self.assertTrue(error.path_truncated)
        self.assertEqual(error.status,'INCOMPLETE')

    def test_work_allocation_and_invalid_budget(self):
        self.refuse('WORK',lambda:codec.pack_native_diagnostic_arrays([0.]*8,budget=budget(limits={'max_work':1})))
        self.refuse('ALLOCATION',lambda:codec.pack_native_diagnostic_arrays([0.]*8,budget=budget(limits={'max_allocation_bytes':1})))
        for kwargs in({'check':None},{'limits':{'max_nodes':500001}},{'limits':{'max_depth':True}},{'usage':{'bytes':-1}},{'usage':{'nodes':True}}):
            self.refuse('INVALID_BUDGET',lambda kwargs=kwargs:codec.CodecBudget(**{'check':lambda phase:None,**kwargs}))
        b=budget();b._counts['nodes']=True
        self.refuse('INVALID_BUDGET',lambda:codec.pack_native_diagnostic_arrays([],budget=b))

    def test_deadline_stop_and_no_refund(self):
        def clock(phase):
            if phase=='codec_after_debit:nodes':
                error=StudioError('stop');error.reason='STOP_REQUESTED';error.status='INCOMPLETE';raise error
        b=budget(check=clock)
        self.refuse('STOP_REQUESTED',lambda:codec.pack_native_diagnostic_arrays([0.]*8,budget=b))
        self.assertGreater(b.usage['nodes'],0)
        b=budget(check=lambda phase:None)
        def deadline(phase):
            if phase=='codec_pack_return':
                error=StudioError('deadline');error.reason='DEADLINE_EXHAUSTED';error.status='INCOMPLETE';raise error
        b._check=deadline
        self.refuse('DEADLINE_EXHAUSTED',lambda:codec.pack_native_diagnostic_arrays([0.]*8,budget=b))
        self.assertGreater(b.usage['bytes'],0)

    def test_invalid_clock_normalized(self):
        def fail(phase):raise OverflowError('clock')
        self.refuse('INVALID_CLOCK',lambda:budget(check=fail))

    def test_cooperative_scalar_decode_and_expansion(self):
        raw=codec.pack_native_diagnostic_arrays(list(range(100)),budget=budget());phases=[]
        codec.unpack_native_diagnostic_arrays(raw,budget=budget(check=phases.append))
        self.assertGreaterEqual(phases.count('codec_reserve:work'),200)
        self.assertIn('codec_unpack_return',phases)

    def test_source_mutation_refused_and_code_binding(self):
        value=[0.]*8
        def mutate(phase):
            if phase=='codec_before_serialization':value[0]=1.
        self.refuse('REFERENCE_CHANGED',lambda:codec.pack_native_diagnostic_arrays(value,budget=budget(check=mutate)))
        raw=codec.pack_native_diagnostic_arrays([],budget=budget())
        self.assertEqual(json.loads(raw)['codec_sha256'],hashlib.sha256(Path(codec.__file__).read_bytes()).hexdigest())

    def test_mutation_at_return_checkpoint_is_refused(self):
        value=list(range(8))
        def mutate(phase):
            if phase=='codec_pack_return':value[0]=99
        self.refuse('REFERENCE_CHANGED',lambda:codec.pack_native_diagnostic_arrays(value,budget=budget(check=mutate)))

    def test_decode_allocation_before_expansion_and_no_partial_return(self):
        raw=codec.pack_native_diagnostic_arrays(list(range(100)),budget=budget())
        phases=[];seen=[False]
        def stop(phase):
            phases.append(phase)
            if phase=='codec_after_base64_decode':seen[0]=True
            if seen[0]and phase=='codec_after_debit:allocation_bytes':
                error=StudioError('stop');error.reason='STOP_REQUESTED';error.status='INCOMPLETE';raise error
        b=budget(check=stop)
        self.refuse('STOP_REQUESTED',lambda:codec.unpack_native_diagnostic_arrays(raw,budget=b))
        self.assertEqual(b.usage['nodes'],101)
        self.assertGreater(b.usage['allocation_bytes'],0)
        self.assertNotIn('codec_unpack_return',phases)

    def test_long_key_path_is_reported_truncated(self):
        key='a'*100;value={key:[]}
        error=self.refuse('DEPTH',lambda:codec.pack_native_diagnostic_arrays(value,budget=budget(limits={'max_depth':0})))
        # A source key is visited at depth one before its associated value.
        self.assertTrue(all(len(part)<=48 for part in error.path))

    def test_code_change_refuses_without_editing_code(self):
        real=codec._code;calls=[0]
        def changed(b):
            code=real(b);calls[0]+=1
            return code if calls[0]==1 else '0'*64
        with patch.object(codec,'_code',changed):
            self.refuse('CODE_CHANGED',lambda:codec.pack_native_diagnostic_arrays([],budget=budget()))

    def test_huge_integer_key_is_controlled_and_preview_bounded(self):
        huge=1<<15000
        self.refuse('INTEGER_TEXT_LIMIT',lambda:codec.pack_native_diagnostic_arrays({huge:0},budget=budget()))
        error=self.refuse('UNSUPPORTED_TYPE',lambda:codec.pack_native_diagnostic_arrays({huge:b'bad'},budget=budget()))
        self.assertTrue(error.path_truncated);self.assertLessEqual(len(error.path[-1]),48)

    def test_vector_iteration_is_never_used(self):
        class IndexedVector(PortableVector):
            def __iter__(self):raise AssertionError('Unbounded iterator must not be used')
        value=[IndexedVector([float(i),-0.])for i in range(4)]
        raw=codec.pack_native_diagnostic_arrays(value,budget=budget(),vector_type=IndexedVector)
        actual=codec.unpack_native_diagnostic_arrays(raw,budget=budget(),vector_type=IndexedVector)
        for expected,observed in zip(value,actual):
            self.assertIs(type(observed),IndexedVector)
            self.assertEqual([bits(expected[i])for i in range(2)],[bits(observed[i])for i in range(2)])

    def test_unicode_fourbyte_hash_and_roundtrip(self):
        self.roundtrip({'text':'😀'*100})

    def test_incompatible_adapter_and_memory_failure_are_classified(self):
        class BrokenVector(PortableVector):
            def __getitem__(self,index):raise RuntimeError('invalid adapter')
        self.refuse('INVALID_NATIVE_INPUT',lambda:codec.pack_native_diagnostic_arrays(BrokenVector([1.,2.]),budget=budget(),vector_type=BrokenVector))
        with patch.object(codec,'_materialize',side_effect=MemoryError):
            self.refuse('ALLOCATION',lambda:codec.pack_native_diagnostic_arrays([0.]*8,budget=budget()))

    def test_wide_unicode_serialization_reservation_covers_buffers(self):
        value={'text':'a'*100000+'😀'};observed={};real=codec.json.dumps
        def measure(*args,**kwargs):
            self.assertTrue(kwargs['ensure_ascii'])
            text=real(*args,**kwargs);line=text+'\n';encoded=line.encode('utf-8')
            observed['minimal_buffers']=sum(sys.getsizeof(v)for v in(text,line,encoded))
            observed['size']=len(encoded)
            return text
        with patch.object(codec.json,'dumps',measure):
            raw=codec.pack_native_diagnostic_arrays(value,budget=budget())
        self.assertEqual(observed['size'],len(raw))
        self.assertTrue(raw.isascii())
        self.assertLessEqual(observed['minimal_buffers'],len(raw)*3+256)

    def test_old_unicode_cap_refuses_before_serialization_without_refund(self):
        value={'text':'a'*100000+'😀'};before=copy.deepcopy(value)
        b=budget(limits={'max_allocation_bytes':733377})
        with patch.object(codec.json,'dumps',side_effect=AssertionError('Serialization must not run'))as serializer:
            error=self.refuse('ALLOCATION',lambda:codec.pack_native_diagnostic_arrays(value,budget=b))
        self.assertFalse(serializer.called);self.assertGreater(error.used+error.requested,error.limit)
        self.assertGreater(b.usage['nodes'],0);self.assertGreater(b.usage['bytes'],0)
        self.exact(before,value,canonical_int=False)

    def test_wide_unicode_complete_allocation_cap_and_minus_one(self):
        value={'text':'a'*100000+'😀'};unlimited=budget()
        raw=codec.pack_native_diagnostic_arrays(value,budget=unlimited)
        cap=unlimited.usage['allocation_bytes']
        exact_budget=budget(limits={'max_allocation_bytes':cap})
        self.assertEqual(codec.pack_native_diagnostic_arrays(value,budget=exact_budget),raw)
        self.assertEqual(exact_budget.usage['allocation_bytes'],cap)
        error=self.refuse('ALLOCATION',lambda:codec.pack_native_diagnostic_arrays(value,budget=budget(limits={'max_allocation_bytes':cap-1})))
        self.assertEqual(error.limit,cap-1)

    def test_encoded_string_size_all_escape_boundaries(self):
        strings=['',chr(0),chr(8),chr(11),chr(31),'"\\\t\n\r\f',chr(32),chr(126),chr(127),
            chr(128),chr(255),chr(256),chr(2047),chr(2048),chr(65535),chr(65536),chr(0x10ffff)]
        for text in strings:
            with self.subTest(codepoints=[ord(c)for c in text]):
                b=budget();expected=len(encoded_dump(text))
                self.assertEqual(codec._encoded_string_size(text,b,('fixture',)),expected)
                self.assertEqual(b.usage['work'],len(text))

    def test_encoded_stats_nested_unicode_keys_receipts_and_blobs(self):
        value={'é漢😀':[1.,2.,3.,4.,5.,6.,7.,8.], 'reports':('é',{'quoted"':'\x00\t\\😀'})}
        _,raw=self.roundtrip(value);packet=json.loads(raw)
        count,size=codec._stats(packet,budget())
        self.assertEqual((count,size+1),(nodes(packet),len(raw)))
        self.assertEqual(raw,encoded_dump(packet)+b'\n')
        self.assertTrue(raw.isascii());self.assertNotIn(b'\xc3\xa9',raw)

    def test_native_utf8_and_encoded_ascii_scopes_stay_distinct(self):
        text='é漢😀';self.assertEqual(codec._utf8_size(text,budget(),()),11)
        self.assertEqual(codec._scalar_size(text,budget(),()),11)
        self.assertEqual(codec._encoded_string_size(text,budget(),()),26)
        value={'é漢😀':('漢',-0.,math.nextafter(1.,math.inf))}
        packet,raw=self.roundtrip(value)
        plan=codec._validate(packet['payload'],budget(),None)
        count,size=codec._expanded_stats(plan,budget())
        self.assertEqual((count,size),(nodes(v3(value)),len(dump(v3(value)))))
        self.assertLess(size,len(encoded_dump(v3(value))))

    def test_encoded_bmp_and_astral_roundtrip_size_growth_is_explicit(self):
        for text in('é'*1000,'漢'*1000,'😀'*1000):
            packet,raw=self.roundtrip({'text':text})
            self.assertGreater(len(raw),len(dump(packet))+1)
            self.assertEqual(packet['receipt']['output_bytes'],len(raw))

    def test_surrogates_refused_in_values_keys_and_direct_encoded_scan(self):
        for text in('\ud800','\udfff','\ud83d\ude00'):
            self.refuse('INVALID_STRING',lambda:codec._encoded_string_size(text,budget(),('key',)))
            for value in(text,{text:'report'},{'report':text}):
                self.refuse('INVALID_STRING',lambda value=value:codec.pack_native_diagnostic_arrays(value,budget=budget()))

    def test_escaped_surrogate_in_packet_is_refused_after_parse(self):
        packet,_=self.roundtrip({'key':'safe'})
        packet['payload']['entries'][0][1]='\ud800'
        # The runtime scanner must refuse it, even though json.dumps itself
        # is willing to emit the invalid code unit in ASCII escaped form.
        self.refuse('INVALID_STRING',lambda:codec.unpack_native_diagnostic_arrays(reseal(packet),budget=budget()))

    def test_ascii_reserve_is_exact_before_dumps(self):
        value={'text':'a'*100000+'😀'};observed={};b=None;real=codec._dumps
        def check(phase):
            if phase=='codec_before_serialization':observed['usage']=b.usage
        def dumps(item):
            observed['raw']=real(item);return observed['raw']
        b=budget(check=check)
        with patch.object(codec,'_dumps',dumps):raw=codec.pack_native_diagnostic_arrays(value,budget=b)
        needed=len(raw)*3+256;before=observed['usage']['allocation_bytes']-needed
        limited=budget(limits={'max_allocation_bytes':before+needed-1})
        with patch.object(codec,'_dumps',side_effect=AssertionError('Dumps must not allocate'))as serializer:
            error=self.refuse('ALLOCATION',lambda:codec.pack_native_diagnostic_arrays(value,budget=limited))
        self.assertEqual((error.used,error.requested,error.limit),(before,needed,before+needed-1))
        self.assertFalse(serializer.called);self.assertGreater(limited.usage['bytes'],0)
        self.assertEqual(limited.usage['allocation_bytes'],before)

    def test_unicode_encoded_output_quota_counts_physical_lf(self):
        value={'汉😀':'é漢😀'};_,raw=self.roundtrip(value)
        self.assertEqual(codec.pack_native_diagnostic_arrays(value,budget=budget(limits={'max_bytes':len(raw)})),raw)
        with patch.object(codec,'_dumps',side_effect=AssertionError('Output cap before dumps'))as serializer:
            self.refuse('BYTES',lambda:codec.pack_native_diagnostic_arrays(value,budget=budget(limits={'max_bytes':len(raw)-1})))
        self.assertFalse(serializer.called)

    def test_dense_unicode_hard_eight_mib_boundary(self):
        raw=codec.pack_native_diagnostic_arrays({'text':''},budget=budget());packet=json.loads(raw)
        maximum=codec._HARD['max_bytes'];packet['receipt']['output_bytes']=maximum
        overhead=len(encoded_dump(packet))+1;count,tail=divmod(maximum-overhead,6)
        value={'text':'é'*count+'a'*tail}
        actual=codec.pack_native_diagnostic_arrays(value,budget=budget())
        self.assertEqual(len(actual),maximum);self.assertEqual(json.loads(actual)['receipt']['output_bytes'],maximum)
        with patch.object(codec,'_dumps',side_effect=AssertionError('Hard cap before dumps'))as serializer:
            self.refuse('BYTES',lambda:codec.pack_native_diagnostic_arrays({'text':value['text']+'a'},budget=budget()))
        self.assertFalse(serializer.called)

    def test_ascii_scanner_observes_same_budget_clock_and_no_refund(self):
        phases=[];b=budget(check=phases.append)
        codec._encoded_string_size('😀'*2049,b,())
        self.assertEqual(phases.count('codec_string_scan'),3);self.assertEqual(b.usage['work'],2049)
        def stop(phase):
            if phase=='codec_string_scan':
                error=StudioError('deadline');error.reason='DEADLINE_EXHAUSTED';error.status='INCOMPLETE';raise error
        b=budget(check=stop)
        self.refuse('DEADLINE_EXHAUSTED',lambda:codec._encoded_string_size('😀'*2049,b,()))
        self.assertEqual(b.usage['work'],2049)

    def test_no_hidden_clock_or_native_import(self):
        import ast
        tree=ast.parse(Path(codec.__file__).read_text(encoding='utf-8'))
        imports={name.name for node in ast.walk(tree)if isinstance(node,ast.Import)for name in node.names}
        self.assertTrue(imports.isdisjoint({'time','mathutils','bpy'}))
        self.assertEqual(codec._HARD['max_nodes'],500000);self.assertEqual(codec._HARD['max_bytes'],8*1024*1024)
        self.assertEqual(codec._HARD['max_depth'],128)


if __name__=='__main__':unittest.main()
