import collections
import glob
import re
import xml.etree.ElementTree as ET

# Upstream assumptions that carry no message of their own (bare assumeTrue/assumeFalse,
# assertj assumeThat): the reason is the guard in the test source, keyed by test class.
GUARDS = [
    (r'Ssl|SSL|Conscrypt|Corretto|Sni|CloseNotify|PemEncoded',
     'SSL provider capability guard in upstream SSLEngineTest/OpenSslEngineTest/SslHandlerTest/'
     'SslContextBuilderTest/PemEncodedTest: the parameter combination needs a feature this run\'s '
     'provider lacks (BoringSSL/AWS-LC-only options, MAX_CERTIFICATE_LIST_BYTES, session cache, ALPN, '
     'TLSv1.3 or KeyManagerFactory mode, per provider: JDK, OpenSSL/BoringSSL, Conscrypt, Amazon Corretto) '
     'or a Conscrypt OpenSSLProvider pairing the test excludes by design'),
    (r'CompositeByteBufTest|SlicedByteBufTest',
     'buffer-type guard in upstream AbstractByteBufTest/AbstractCompositeByteBufTest/SlicedByteBufTest: '
     'test applies only to buffers with maxCapacity == Integer.MAX_VALUE, a single nioBuffer, '
     'or writable (non read-only) buffers'),
    (r'ByteBufUtilTest', 'ByteBufUtilTest: case applies only to the BufferType.HEAP_UNPOOLED parameter'),
    (r'RecyclerTest', 'RecyclerTest.assumeIsPooling: case applies only to pooling Recycler owner types'),
    (r'VirtualThreadCheckTest', 'VirtualThreadCheckTest: virtual threads need Java 21+, build JDK is 11'),
    (r'PlatformDependentTest', 'PlatformDependentTest: DirectByteBuffer no-cleaner constructor is not '
     'accessible on JDK 11 without --add-opens'),
    (r'CertificateBuilderTest', 'CertificateBuilderTest: key algorithm (or its signing) not supported by '
     'the JDK 11 providers, or rsa4096/rsa8192 excluded by the test itself'),
    (r'DefaultEventLoopTest', 'AbstractSingleThreadEventLoopTest: DefaultEventLoop does not support '
     'channel iteration (assumeTrue(supportsChannelIteration()))'),
    (r'DomainDatagramUnicastTest', 'DatagramUnicastTest.testReceiveEmptyDatagrams: java.net.DatagramSocket '
     'cannot bind a Unix domain socket address (unsupported address type)'),
]
EMPTY_CLASS = [
    (r'PlatformDependent0Test', 'class-level assumeTrue(hasUnsafe() && hasDirectBufferNoCleanerConstructor()): '
     'the no-cleaner DirectByteBuffer constructor is not accessible on JDK 11, same cause as the NoCleaner '
     'ByteBuf skips'),
    (r'OpenSslCertificateCompressionTest|OpenSslPrivateKeyMethodTest',
     'class-level assumeTrue(OpenSsl.isBoringSSL() || OpenSsl.isAWSLC()) / OpenSsl.isTlsv13Supported()'),
    (r'OpenSslCredentialBuilderTest', 'class-level assumeTrue(OpenSslCredential.isAvailable()), BoringSSL-only API'),
]
GENERIC = re.compile(r'^\s*$|assumption is not (true|false)\s*$|TestAbortedException:\s*$|^skipped without a message$')


def explain(table, cls, default):
    for pat, why in table:
        if re.search(pat, cls):
            return why
    return default


tot = collections.Counter()
per_mod = collections.defaultdict(collections.Counter)
skips = collections.defaultdict(collections.Counter)
empty = []
for f in sorted(glob.glob('**/target/surefire-reports/TEST-*.xml', recursive=True)):
    mod = f.split('/target/')[0]
    try:
        root = ET.parse(f).getroot()
    except ET.ParseError:
        continue
    for s in ([root] if root.tag == 'testsuite' else root.findall('testsuite')):
        c = collections.Counter({k: int(s.get(k, 0)) for k in ('tests', 'failures', 'errors', 'skipped')})
        tot.update(c)
        per_mod[mod].update(c)
        if c['tests'] == 0:
            empty.append(s.get('name', '').split('.')[-1])
        for tc in s.findall('testcase'):
            sk = tc.find('skipped')
            if sk is None:
                continue
            cls = tc.get('classname', '').split('.')[-1]
            reason = (sk.get('message') or (sk.text or '').strip() or 'skipped without a message').splitlines()[0]
            reason = reason.replace('org.opentest4j.TestAbortedException:', '').strip()
            m = re.match(r'public .* ([\w$.]+)\.(\w+)\(.*is @Disabled', reason)
            if m:
                reason = '@Disabled in upstream source (no reason text)'
            elif GENERIC.search(reason):
                reason = explain(GUARDS, cls, 'upstream assumption without message: ' + reason)
            skips[reason[:600]][cls] += 1

print('==== Skipped tests: one line per reason -> test class (skipped count) ====')
for reason, classes in sorted(skips.items(), key=lambda kv: -sum(kv[1].values())):
    names = ', '.join('%s(%d)' % kv for kv in sorted(classes.items()))
    if len(names) > 360:
        names = names[:360] + ', ...'
    print('SKIPPED %d: %s -> %s' % (sum(classes.values()), reason, names))
for cls in empty:
    print('RAN 0 TESTS: %s -> %s' % (cls, explain(EMPTY_CLASS, cls, 'no test methods matched')))
print('==== Surefire results per module ====')
for mod, c in sorted(per_mod.items()):
    print('%-30s run=%d passed=%d failures=%d errors=%d skipped=%d' % (
        mod, c['tests'], c['tests'] - c['failures'] - c['errors'] - c['skipped'],
        c['failures'], c['errors'], c['skipped']))
print('==== TOTAL: tests run=%d, passed=%d, failures=%d, errors=%d, skipped=%d ====' % (
    tot['tests'], tot['tests'] - tot['failures'] - tot['errors'] - tot['skipped'],
    tot['failures'], tot['errors'], tot['skipped']))
