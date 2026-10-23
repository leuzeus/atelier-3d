"""Private lossless storage, independent of the native V3 DTO and admission."""
import base64
import hashlib
import json
import math
from pathlib import Path
import struct
from types import MappingProxyType

from .core import StudioError

DISCRIMINANT = 'NATIVE_DIAGNOSTIC_ARRAY_DTO_V1'
_HARD = {'max_nodes':500000, 'max_bytes':8388608, 'max_depth':128,
         'max_work':100000000, 'max_allocation_bytes':268435456}
_MIN_ELEMENTS = 8
_INT_MIN, _INT_MAX = -(1<<63), (1<<63)-1
_KINDS = {'LIST','TUPLE','VECTOR'}


def _preview(part):
    if type(part)is int and part.bit_length()>128:return '<int:'+str(part.bit_length())+'bits>',True
    if type(part)is str:return part[:48],len(part)>48
    if type(part)in(int,float,bool,type(None)):
        text=str(part);return text[:48],len(text)>48
    return '<'+type(part).__name__[:40]+'>',True


def _fail(reason, path=(), depth=None, **details):
    error = StudioError('Native diagnostic storage: '+reason)
    error.reason = reason
    error.status = 'INCOMPLETE' if reason in ('NODES','DEPTH','BYTES','WORK','ALLOCATION','DEADLINE_EXHAUSTED','STOP_REQUESTED') else 'REFUSED'
    error.qualification = 'NONE'
    preview=[_preview(x)for x in path[:12]]
    error.path = [part for part,_ in preview]
    error.path_truncated = len(path)>12 or any(truncated for _,truncated in preview)
    error.observed_depth = depth
    for name, value in details.items():setattr(error,name,value)
    raise error


class CodecBudget:
    """Caller-owned cumulative storage ledger; check supplies the existing clock.

    Allocation bytes are conservative reservations, not measured RSS. Nothing
    creates a clock, deadline or refund. Initial usage includes earlier outputs.
    """
    def __init__(self, *, check, limits=None, usage=None):
        if not callable(check):_fail('INVALID_BUDGET')
        limits = {} if limits is None else limits
        if type(limits)is not dict or set(limits)-set(_HARD):_fail('INVALID_BUDGET')
        caps={**_HARD,**limits}
        if any(type(v)is not int or not 0<=v<=_HARD[k] for k,v in caps.items()):_fail('INVALID_BUDGET')
        counts={k:0 for k in ('nodes','bytes','work','allocation_bytes')}
        if usage is not None:
            if type(usage)is not dict or set(usage)-set(counts):_fail('INVALID_BUDGET')
            counts.update(usage)
        if any(type(v)is not int or not 0<=v<=caps['max_'+k] for k,v in counts.items()):_fail('INVALID_BUDGET')
        self.limits=MappingProxyType(caps);self._counts=counts;self._check=check
        self.check('codec_budget_created')

    @property
    def usage(self):return dict(self._counts)

    def check(self, phase):
        try:self._check(phase)
        except StudioError as error:
            error.qualification='NONE';raise
        except Exception:_fail('INVALID_CLOCK')

    def reserve(self, name, count, path=()):
        self.check('codec_reserve:'+name)
        if name not in self._counts or type(count)is not int or count<0:_fail('INVALID_BUDGET',path)
        if self._counts[name]+count>self.limits['max_'+name]:
            _fail({'nodes':'NODES','bytes':'BYTES','work':'WORK','allocation_bytes':'ALLOCATION'}[name],path,
                  used=self._counts[name],requested=count,limit=self.limits['max_'+name])
        self._counts[name]+=count
        self.check('codec_after_debit:'+name)

    def step(self, path=(), depth=0):
        if depth>self.limits['max_depth']:_fail('DEPTH',path,depth)
        self.reserve('work',1,path)


def _budget(value):
    if type(value)is not CodecBudget:_fail('INVALID_BUDGET')
    if(type(value.limits)is not MappingProxyType or set(value.limits)!=set(_HARD)or
       any(type(v)is not int or not 0<=v<=_HARD[k]for k,v in value.limits.items())or
       type(value._counts)is not dict or set(value._counts)!={'nodes','bytes','work','allocation_bytes'}or
       any(type(v)is not int or not 0<=v<=value.limits['max_'+k]for k,v in value._counts.items())or
       not callable(value._check)):_fail('INVALID_BUDGET')
    value.check('codec_entry')
    return value


def _vector_type(value):
    if value is not None and(type(value)is not type or value in(list,tuple,dict,str,int,float,bool,bytes)):_fail('INVALID_VECTOR_TYPE')
    return value


def _kind(item, vector_type):
    t=type(item)
    if t is list:return 'LIST'
    if t is tuple:return 'TUPLE'
    if vector_type is not None and t is vector_type:return 'VECTOR'
    return None


def _utf8_size(text, budget, path):
    n=2;budget.reserve('work',len(text),path)
    for i,c in enumerate(text):
        if i%1024==0:budget.check('codec_string_scan')
        x=ord(c)
        if 0xd800<=x<=0xdfff:_fail('INVALID_STRING',path)
        if c in '"\\':n+=2
        elif x<32:n+=2 if c in '\b\f\n\r\t' else 6
        else:n+=1 if x<128 else 2 if x<2048 else 3 if x<65536 else 4
    return n


def _scalar_size(value,budget,path):
    t=type(value)
    if t is str:return _utf8_size(value,budget,path)
    if t is type(None):return 4
    if t is bool:return 4 if value else 5
    if t is float:
        if not math.isfinite(value):_fail('NONFINITE',path)
        budget.reserve('allocation_bytes',64,path);return len(repr(value))
    if t is int:
        budget.reserve('work',value.bit_length()+1,path)
        budget.reserve('allocation_bytes',value.bit_length()*30103//100000+3,path)
        try:return len(str(value))
        except ValueError:_fail('INTEGER_TEXT_LIMIT',path)
    _fail('UNSUPPORTED_TYPE',path)


def _encoded_string_size(text,budget,path):
    """Exact ASCIIescaped JSON size, only for the closed encoded DTO."""
    n=2;budget.reserve('work',len(text),path)
    for i,c in enumerate(text):
        if i%1024==0:budget.check('codec_string_scan')
        x=ord(c)
        if 0xd800<=x<=0xdfff:_fail('INVALID_STRING',path)
        if c in '"\\':n+=2
        elif x<32:n+=2 if c in '\b\f\n\r\t'else 6
        else:n+=1 if x<127 else 6 if x<65536 else 12
    return n


def _hash_native(value,budget,vector_type):
    h=hashlib.sha256();active=set()
    def feed(raw):h.update(struct.pack('<Q',len(raw)));h.update(raw)
    def prefix(tag,raw):
        h.update(struct.pack('<Q',len(tag)+len(raw)));h.update(tag);h.update(raw)
    def visit(item,path=(),depth=0):
        budget.step(path,depth);budget.reserve('allocation_bytes',128,path)
        t=type(item);kind=_kind(item,vector_type)
        if t in (dict,list,tuple)or kind=='VECTOR':
            if id(item)in active:_fail('CYCLE',path)
            active.add(id(item));feed(('DICT'if t is dict else kind).encode())
            try:
                feed(struct.pack('<Q',len(item)))
                if t is dict:
                    for k,v in item.items():visit(k,path+('key',),depth+1);visit(v,path+(k,),depth+1)
                else:
                    if kind=='VECTOR'and(len(item)not in(2,3)or any(type(item[i])is not float for i in range(len(item)))):_fail('UNSUPPORTED_VECTOR',path)
                    for i in range(len(item)):visit(item[i],path+(i,),depth+1)
            finally:active.remove(id(item))
        elif t is float:
            if not math.isfinite(item):_fail('NONFINITE',path)
            budget.reserve('allocation_bytes',8,path);prefix(b'F',struct.pack('<d',item))
        elif t is int:
            size=(item.bit_length()+8)//8;budget.reserve('allocation_bytes',size,path)
            budget.reserve('work',size,path)
            prefix(b'I',item.to_bytes(size,'little',signed=True))
        elif t is str:
            _utf8_size(item,budget,path);budget.reserve('allocation_bytes',len(item)*4,path)
            budget.reserve('work',len(item)*4,path);prefix(b'S',item.encode('utf-8'))
        elif t is bool:feed(b'B1'if item else b'B0')
        elif t is type(None):feed(b'N')
        else:_fail('UNSUPPORTED_TYPE',path)
    visit(value);budget.check('codec_native_hash_complete');return h.hexdigest()


class _Blob:
    def __init__(self, value, shape, dtype, container, rows, integer_map=False):
        self.value=value;self.shape=shape;self.dtype=dtype;self.container=container
        self.rows=rows;self.integer_map=integer_map
        self.elements=math.prod(shape);self.length=4*((self.elements*8+2)//3)

    def cells(self):
        if self.integer_map:
            for key in self.rows:yield key;yield self.value[key]
        elif len(self.shape)==1:
            yield from self.value
        else:
            for row in self.value:
                for j in range(self.shape[1]):yield row[j]


def _array(item,budget,vector_type,path):
    kind=_kind(item,vector_type)
    if kind not in ('LIST','TUPLE')or not item:return None
    first=type(item[0]);shape=[len(item)];row_kind=None
    if first in (int,float):values=item
    else:
        row_kind=_kind(item[0],vector_type)
        if row_kind is None or not len(item[0]):return None
        width=len(item[0]);shape.append(width)
        for row in item:
            budget.step(path)
            if _kind(row,vector_type)!=row_kind or len(row)!=width:return None
        if row_kind=='VECTOR'and width not in(2,3):_fail('UNSUPPORTED_VECTOR',path)
        values=(row[j]for row in item for j in range(width));first=type(item[0][0])
    if math.prod(shape)<_MIN_ELEMENTS or first not in(int,float):return None
    for v in values:
        budget.step(path)
        if type(v)is not first:return None
        if first is int and not _INT_MIN<=v<=_INT_MAX:return None
        if first is float and not math.isfinite(v):_fail('NONFINITE',path)
    return _Blob(item,shape,'INT64_LE'if first is int else'BINARY64_LE',kind,row_kind)


def _plan(item,budget,vector_type,path=(),depth=0,active=None):
    budget.step(path,depth);budget.reserve('allocation_bytes',512,path)
    active=set()if active is None else active;t=type(item);kind=_kind(item,vector_type)
    if t not in(dict,list,tuple)and kind!='VECTOR':_scalar_size(item,budget,path);return item
    if id(item)in active:_fail('CYCLE',path)
    active.add(id(item))
    try:
        if t is dict:
            budget.reserve('allocation_bytes',len(item)*16+128,path);keys=list(item)
            if all(type(k)is str for k in keys):key_kind='STR'
            elif keys and all(type(k)is int for k in keys):
                key_kind='INT';budget.reserve('work',len(keys)*len(keys).bit_length(),path)
                budget.check('codec_before_key_sort');keys.sort();budget.check('codec_after_key_sort')
            else:_fail('AMBIGUOUS_KEYS',path)
            if key_kind=='INT'and len(keys)*2>=_MIN_ELEMENTS:
                okay=True
                for k in keys:
                    budget.step(path)
                    if type(item[k])is not int or not(_INT_MIN<=k<=_INT_MAX and _INT_MIN<=item[k]<=_INT_MAX):okay=False;break
                if okay:return {'tag':'INT_MAP_ARRAY','shape':[len(keys),2],'dtype':'INT64_LE',
                                  'data':_Blob(item,[len(keys),2],'INT64_LE','INTEGER_MAP',keys,True)}
            budget.reserve('allocation_bytes',len(keys)*128+128,path)
            return {'tag':'MAP','key_type':key_kind,'entries':[[k,_plan(item[k],budget,vector_type,path+(k,),depth+1,active)]for k in keys]}
        if kind=='VECTOR'and(len(item)not in(2,3)or any(type(item[i])is not float for i in range(len(item)))):_fail('UNSUPPORTED_VECTOR',path)
        blob=_array(item,budget,vector_type,path)
        if blob:return {'tag':'ARRAY','shape':blob.shape,'dtype':blob.dtype,'container':blob.container,
                        'row_container':blob.rows,'data':blob}
        budget.reserve('allocation_bytes',len(item)*16+128,path)
        return {'tag':kind,'items':[_plan(item[i],budget,vector_type,path+(i,),depth+1,active)for i in range(len(item))]}
    finally:active.remove(id(item))


def _stats(item,budget,path=(),depth=0):
    budget.step(path,depth)
    if isinstance(item,_Blob):return 1,item.length+2
    t=type(item)
    if t is dict:
        nodes=1;size=2+max(0,len(item)-1)
        for k,v in item.items():
            budget.step(path+(k,),depth+1);nodes+=1
            size+=(_encoded_string_size(k,budget,path)if type(k)is str else _scalar_size(k,budget,path))+1
            n,b=_stats(v,budget,path+(k,),depth+1);nodes+=n;size+=b
        return nodes,size
    if t is list:
        nodes=1;size=2+max(0,len(item)-1)
        for i,v in enumerate(item):
            n,b=_stats(v,budget,path+(i,),depth+1);nodes+=n;size+=b
        return nodes,size
    return 1,_encoded_string_size(item,budget,path)if t is str else _scalar_size(item,budget,path)


def _materialize(item,budget,path=()):
    budget.step(path)
    if isinstance(item,_Blob):
        budget.reserve('allocation_bytes',item.elements*8+item.length*2+128,path)
        raw=bytearray(item.elements*8);fmt='<q'if item.dtype=='INT64_LE'else'<d'
        for i,v in enumerate(item.cells()):
            budget.step(path+(i,));budget.reserve('allocation_bytes',128,path+(i,))
            struct.pack_into(fmt,raw,i*8,v)
        budget.check('codec_before_base64');encoded=base64.b64encode(raw).decode('ascii')
        budget.check('codec_after_base64');return encoded
    if type(item)is dict:
        budget.reserve('allocation_bytes',128+len(item)*64,path)
        return {k:_materialize(v,budget,path+(k,))for k,v in item.items()}
    if type(item)is list:
        budget.reserve('allocation_bytes',128+len(item)*16,path)
        return [_materialize(v,budget,path+(i,))for i,v in enumerate(item)]
    return item


def _code(budget):
    p=Path(__file__);budget.check('codec_before_code_read');size=p.stat().st_size
    budget.reserve('allocation_bytes',size);budget.reserve('work',size)
    raw=p.read_bytes()
    if len(raw)!=size:_fail('CODE_CHANGED')
    result=hashlib.sha256(raw).hexdigest();budget.check('codec_after_code_hash');return result


def _dumps(item):
    return (json.dumps(item,ensure_ascii=True,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')


def _pack(value, *, budget, vector_type=None):
    """Return one JSON+LF bytes artifact; all wrappers/receipt are charged."""
    b=_budget(budget);vector_type=_vector_type(vector_type);code=_code(b)
    before=_hash_native(value,b,vector_type);plan=_plan(value,b,vector_type)
    packet={'discriminant':DISCRIMINANT,'version':1,'purpose':'TEST_ONLY','qualification':'NONE',
            'codec_sha256':code,'payload':plan,'receipt':{'scope':'ENCODED_STORAGE_NOT_NATIVE_LEDGER',
            'output_nodes':0,'output_bytes':0}}
    nodes,_=_stats(packet,b);packet['receipt']['output_nodes']=nodes
    for _ in range(10):
        _,size=_stats(packet,b);size+=1
        if packet['receipt']['output_bytes']==size:break
        packet['receipt']['output_bytes']=size
    else:_fail('INVALID_ACCOUNTING')
    b.reserve('nodes',nodes);b.reserve('bytes',size)
    materialized=_materialize(packet,b)
    # The closed DTO is ASCIIescaped: both Python strings are one-byte ASCII.
    # Reserve their two buffers, JSON+LF bytes and headers before allocation.
    # Native hashing and expanded V3 byte accounting retain their UTF-8 scope.
    b.reserve('allocation_bytes',size*3+256)
    b.check('codec_before_serialization')
    raw=_dumps(materialized)
    if len(raw)!=size:_fail('INVALID_ACCOUNTING')
    b.check('codec_pack_return')
    if _code(b)!=code:_fail('CODE_CHANGED')
    if _hash_native(value,b,vector_type)!=before:_fail('REFERENCE_CHANGED')
    return raw


def _read_json(raw,budget):
    if type(raw)is not bytes or not raw.endswith(b'\n')or raw.endswith(b'\r\n'):_fail('INVALID_DTO')
    if len(raw)>_HARD['max_bytes']:_fail('BYTES')
    budget.reserve('work',len(raw));depth=0;quoted=False;escape=False
    for i,c in enumerate(raw):
        if i%1024==0:budget.check('codec_before_parse_scan')
        if quoted:
            if escape:escape=False
            elif c==92:escape=True
            elif c==34:quoted=False
        elif c==34:quoted=True
        elif c in(91,123):
            depth+=1
            if depth>budget.limits['max_depth']+1:_fail('DEPTH',('json_byte',i),depth-1)
        elif c in(93,125):depth-=1
    # Bound parser allocations before it can materialize a JSON object graph.
    budget.reserve('allocation_bytes',min(_HARD['max_nodes'],len(raw))*128+len(raw)*16+128)
    def pairs(values):
        d={}
        for k,v in values:
            if k in d:_fail('DUPLICATE_KEY')
            d[k]=v
        return d
    def number(s):
        value=float(s)
        if not math.isfinite(value):_fail('NONFINITE')
        return value
    def constant(s):_fail('NONFINITE')
    try:value=json.loads(raw,object_pairs_hook=pairs,parse_float=number,parse_constant=constant)
    except StudioError:raise
    except (ValueError,UnicodeError,RecursionError):_fail('INVALID_DTO')
    budget.check('codec_after_parse');return value


class _Decoded:
    def __init__(self,node,raw):self.node=node;self.raw=raw
    def values(self,budget,path):
        fmt='<q'if self.node['dtype']=='INT64_LE'else'<d'
        for i in range(len(self.raw)//8):
            budget.step(path+(i,));budget.reserve('allocation_bytes',128,path+(i,))
            yield struct.unpack_from(fmt,self.raw,i*8)[0]


def _tag(item,path):
    tag=item.get('tag')
    expected={'ARRAY':{'tag','shape','dtype','container','row_container','data'},
      'INT_MAP_ARRAY':{'tag','shape','dtype','data'},'MAP':{'tag','key_type','entries'},
      'LIST':{'tag','items'},'TUPLE':{'tag','items'},'VECTOR':{'tag','items'}}
    if type(tag)is not str or tag not in expected or set(item)!=expected[tag]:_fail('INVALID_TAG',path)
    return tag


def _shape_info(node,path):
    tag=node['tag'];shape=node['shape']
    if(type(shape)is not list or len(shape)not in(1,2)or any(type(v)is not int or v<1 for v in shape)):_fail('INVALID_SHAPE',path)
    count=math.prod(shape)
    if count<_MIN_ELEMENTS:_fail('INVALID_SHAPE',path)
    if type(node['dtype'])is not str or node['dtype']not in('INT64_LE','BINARY64_LE'):_fail('INVALID_DTYPE',path)
    if tag=='INT_MAP_ARRAY':
        if len(shape)!=2 or shape[1]!=2 or node['dtype']!='INT64_LE':_fail('INVALID_SHAPE',path)
    else:
        if type(node['container'])is not str or node['container']not in('LIST','TUPLE'):_fail('INVALID_CONTAINER',path)
        if(len(shape)==1 and node['row_container']is not None or
           len(shape)==2 and(type(node['row_container'])is not str or node['row_container']not in _KINDS)):_fail('INVALID_CONTAINER',path)
        if node['row_container']=='VECTOR'and(shape[1]not in(2,3)or node['dtype']!='BINARY64_LE'):_fail('UNSUPPORTED_VECTOR',path)
    data=node['data'];expected=4*((count*8+2)//3)
    if type(data)is not str or len(data)!=expected:_fail('INVALID_BASE64',path)
    return count,expected


def _blob(node,budget,path):
    count,expected=_shape_info(node,path);data=node['data']
    budget.reserve('work',count,path)
    budget.reserve('allocation_bytes',expected*3+count*8+128,path)
    budget.check('codec_before_base64_decode')
    try:
        encoded=data.encode('ascii');raw=base64.b64decode(encoded,validate=True)
        if len(raw)!=count*8 or base64.b64encode(raw)!=encoded:_fail('INVALID_BASE64',path)
    except (ValueError,UnicodeError):_fail('INVALID_BASE64',path)
    budget.check('codec_after_base64_decode');return _Decoded(node,raw)


def _expanded_nodes(item,budget,vector_type,path=(),depth=0):
    """Closed metadata only: refuse expansion before decoding numeric buffers."""
    budget.step(path,depth)
    if type(item)is not dict:
        _scalar_size(item,budget,path);return 1
    tag=_tag(item,path)
    if tag in('ARRAY','INT_MAP_ARRAY'):
        count,_=_shape_info(item,path);shape=item['shape']
        if tag=='INT_MAP_ARRAY':
            budget.step(path+('entries','value'),depth+3);return 5+3*shape[0]
        outer=1 if item['container']=='LIST'else 5
        row_depth=depth+(1 if item['container']=='LIST'else 2)
        if len(shape)==1:
            budget.step(path+('value',),row_depth);return outer+count
        row_kind=item['row_container']
        if row_kind=='VECTOR'and vector_type is None:_fail('UNSUPPORTED_VECTOR',path)
        budget.step(path+('row','value'),row_depth+(1 if row_kind=='LIST'else 2))
        return outer+shape[0]*(1 if row_kind=='LIST'else 5)+count
    if tag=='MAP':
        entries=item['entries'];kind=item['key_type']
        if type(entries)is not list or type(kind)is not str or kind not in('STR','INT'):_fail('INVALID_MAP',path)
        n=1 if kind=='STR'else 5;keys=set();previous=None
        budget.reserve('allocation_bytes',128+len(entries)*128,path)
        child_depth=depth+(1 if kind=='STR'else 3)
        for i,row in enumerate(entries):
            budget.step(path+(i,),child_depth)
            if type(row)is not list or len(row)!=2:_fail('INVALID_MAP',path+(i,))
            k,v=row
            if type(k)is not(str if kind=='STR'else int)or k in keys:_fail('INVALID_MAP',path+(i,))
            if kind=='INT'and previous is not None and k<=previous:_fail('INVALID_MAP',path+(i,))
            previous=k;keys.add(k);_scalar_size(k,budget,path)
            n+=(1 if kind=='STR'else 2)+_expanded_nodes(v,budget,vector_type,path+(k,),child_depth)
        return n
    items=item['items']
    if type(items)is not list:_fail('INVALID_TAG',path)
    if tag=='VECTOR'and(vector_type is None or len(items)not in(2,3)or any(type(v)is not float for v in items)):_fail('UNSUPPORTED_VECTOR',path)
    n=1 if tag=='LIST'else 5;child_depth=depth+(1 if tag=='LIST'else 2)
    for i,v in enumerate(items):n+=_expanded_nodes(v,budget,vector_type,path+(i,),child_depth)
    return n


def _validate(item,budget,vector_type,path=(),depth=0):
    budget.step(path,depth)
    if type(item)is not dict:_scalar_size(item,budget,path);return item
    tag=_tag(item,path)
    budget.reserve('allocation_bytes',128,path)
    if tag in('ARRAY','INT_MAP_ARRAY'):
        if tag=='ARRAY'and item['row_container']=='VECTOR'and vector_type is None:_fail('UNSUPPORTED_VECTOR',path)
        return _blob(item,budget,path)
    if tag=='MAP':
        entries=item['entries'];kind=item['key_type']
        if type(entries)is not list or kind not in('STR','INT'):_fail('INVALID_MAP',path)
        keys=set();previous=None;result=[]
        budget.reserve('allocation_bytes',len(entries)*128,path)
        for i,row in enumerate(entries):
            if type(row)is not list or len(row)!=2:_fail('INVALID_MAP',path+(i,))
            k,v=row
            if type(k)is not(str if kind=='STR'else int)or k in keys:_fail('INVALID_MAP',path+(i,))
            if kind=='INT'and previous is not None and k<=previous:_fail('INVALID_MAP',path+(i,))
            keys.add(k);previous=k;_scalar_size(k,budget,path)
            result.append((k,_validate(v,budget,vector_type,path+(k,),depth+1)))
        return ('MAP',kind,result)
    if type(item['items'])is not list:_fail('INVALID_TAG',path)
    if tag=='VECTOR'and(vector_type is None or len(item['items'])not in(2,3)or any(type(v)is not float for v in item['items'])):_fail('UNSUPPORTED_VECTOR',path)
    budget.reserve('allocation_bytes',len(item['items'])*128,path)
    return (tag,[_validate(v,budget,vector_type,path+(i,),depth+1)for i,v in enumerate(item['items'])])


def _sequence_totals(kind,n,size,count):
    size+=max(0,count-1)
    if kind=='LIST':return 1+n,2+size
    key='native_type'if kind=='VECTOR'else'native_sequence_type'
    val='mathutils.Vector'if kind=='VECTOR'else'TUPLE'
    overhead=len(json.dumps({key:val,'values':[]},separators=(',',':')))
    return 5+n,overhead+size


def _sequence_stats(kind, children):
    return _sequence_totals(kind,sum(x[0]for x in children),sum(x[1]for x in children),len(children))


def _expanded_stats(item,budget,path=()):
    budget.step(path)
    if isinstance(item,_Decoded):
        node=item.node;values=iter(item.values(budget,path));previous=None
        if node['tag']=='INT_MAP_ARRAY':
            n=5;size=len('{"native_mapping_type":"INTEGER_KEYS","entries":[]}')
            for i in range(node['shape'][0]):
                k,v=next(values),next(values);budget.step(path+(i,))
                if previous is not None and k<=previous:_fail('INVALID_MAP',path)
                previous=k;n+=3;size+=3+_scalar_size(k,budget,path)+_scalar_size(v,budget,path)+(1 if i else 0)
            return n,size
        row_n=row_b=0;width=node['shape'][-1];count=node['shape'][0]if len(node['shape'])==2 else 1
        for i in range(count):
            child_b=0
            for j in range(width):
                v=next(values);child_b+=_scalar_size(v,budget,path+(i,j))
            n,b=_sequence_totals(node['row_container']if len(node['shape'])==2 else node['container'],width,child_b,width)
            row_n+=n;row_b+=b
        return _sequence_totals(node['container'],row_n,row_b,count)if len(node['shape'])==2 else(n,b)
    if type(item)is tuple:
        if item[0]=='MAP':
            _,kind,entries=item;children=[]
            budget.reserve('allocation_bytes',len(entries)*128+128,path)
            for k,v in entries:
                n,b=_expanded_stats(v,budget,path);children.append((1+n,_scalar_size(k,budget,path)+b+1))
            if kind=='STR':return 1+sum(x[0]for x in children),2+sum(x[1]for x in children)+max(0,len(children)-1)
            return 5+sum(x[0]+1 for x in children),len('{"native_mapping_type":"INTEGER_KEYS","entries":[]}')+sum(x[1]+2 for x in children)+max(0,len(children)-1)
        n=size=0
        for i,v in enumerate(item[1]):
            child_n,child_b=_expanded_stats(v,budget,path+(i,));n+=child_n;size+=child_b
        return _sequence_totals(item[0],n,size,len(item[1]))
    return 1,_scalar_size(item,budget,path)


def _build(item,budget,vector_type,path=()):
    budget.step(path)
    def sequence(kind,values):
        if kind=='LIST':return values
        if kind=='TUPLE':return tuple(values)
        budget.check('codec_before_vector_constructor')
        try:result=vector_type(values)
        except StudioError:raise
        except Exception:_fail('VECTOR_ROUNDTRIP',path)
        budget.check('codec_after_vector_constructor')
        if type(result)is not vector_type or len(result)!=len(values)or any(type(result[i])is not float or struct.pack('<d',result[i])!=struct.pack('<d',v)for i,v in enumerate(values)):_fail('VECTOR_ROUNDTRIP',path)
        return result
    if isinstance(item,_Decoded):
        node=item.node;values=iter(item.values(budget,path));count=math.prod(node['shape'])
        budget.reserve('allocation_bytes',count*128+128,path)
        if node['tag']=='INT_MAP_ARRAY':return {next(values):next(values)for _ in range(node['shape'][0])}
        if len(node['shape'])==1:return sequence(node['container'],[next(values)for _ in range(count)])
        rows=[]
        for i in range(node['shape'][0]):
            budget.step(path+(i,));rows.append(sequence(node['row_container'],[next(values)for _ in range(node['shape'][1])]))
        return sequence(node['container'],rows)
    if type(item)is tuple:
        if item[0]=='MAP':
            budget.reserve('allocation_bytes',128+len(item[2])*128,path)
            return {k:_build(v,budget,vector_type,path+(k,))for k,v in item[2]}
        budget.reserve('allocation_bytes',128+len(item[1])*128,path)
        return sequence(item[0],[_build(v,budget,vector_type,path+(i,))for i,v in enumerate(item[1])])
    return item


def _unpack(raw, *, budget, vector_type=None):
    """Explicit expansion, charged as the complete expanded V3 representation."""
    b=_budget(budget);vector_type=_vector_type(vector_type);code=_code(b);packet=_read_json(raw,b)
    if(type(packet)is not dict or set(packet)!={'discriminant','version','purpose','qualification','codec_sha256','payload','receipt'}or
       packet['discriminant']!=DISCRIMINANT or type(packet['version'])is not int or packet['version']!=1 or
       packet['purpose']!='TEST_ONLY'or packet['qualification']!='NONE'or packet['codec_sha256']!=code):_fail('INVALID_DTO')
    receipt=packet['receipt']
    if type(receipt)is not dict or set(receipt)!={'scope','output_nodes','output_bytes'}or receipt['scope']!='ENCODED_STORAGE_NOT_NATIVE_LEDGER':_fail('INVALID_RECEIPT')
    nodes,size=_stats(packet,b)
    if nodes>_HARD['max_nodes']:_fail('NODES')
    if type(receipt['output_nodes'])is not int or receipt['output_nodes']!=nodes or type(receipt['output_bytes'])is not int or receipt['output_bytes']!=len(raw)or size+1!=len(raw):_fail('INVALID_RECEIPT')
    preflight_nodes=_expanded_nodes(packet['payload'],b,vector_type)
    b.reserve('nodes',preflight_nodes)
    plan=_validate(packet['payload'],b,vector_type)
    expanded_nodes,expanded_bytes=_expanded_stats(plan,b)
    if expanded_nodes!=preflight_nodes:_fail('INVALID_ACCOUNTING')
    b.reserve('bytes',expanded_bytes)
    result=_build(plan,b,vector_type)
    if _code(b)!=code:_fail('CODE_CHANGED')
    b.check('codec_unpack_return');return result


def pack_native_diagnostic_arrays(value, *, budget, vector_type=None):
    """One complete JSON+LF artifact, or a classified refusal without refund."""
    try:return _pack(value,budget=budget,vector_type=vector_type)
    except StudioError:raise
    except MemoryError:_fail('ALLOCATION')
    except OSError:_fail('CODE_IO_FAILURE')
    except (ValueError,TypeError,IndexError,KeyError,RuntimeError,struct.error):_fail('INVALID_NATIVE_INPUT')


def unpack_native_diagnostic_arrays(raw, *, budget, vector_type=None):
    """Explicit complete expansion; no caller, clock or native admission."""
    try:return _unpack(raw,budget=budget,vector_type=vector_type)
    except StudioError:raise
    except MemoryError:_fail('ALLOCATION')
    except OSError:_fail('CODE_IO_FAILURE')
    except (ValueError,TypeError,IndexError,KeyError,RuntimeError,struct.error):_fail('INVALID_DTO')
