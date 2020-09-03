import os
import re
import json
from lxml import etree
from git import Repo
import wave
import contextlib
import scipy.io.wavfile as wav
import datetime

EAF_TIME_MULTIPLIER = 1000  # time stamps are in milliseconds


class EafStats:
    """
    Contains methods to collect some statistics about ELAN files in your corpus.
    """

    mediaExtensions = {'.wav'}
    rxSpaces = re.compile('[ \t]+')
    rxLetters = re.compile('\w+')
    rxStripDir = re.compile('^.*[/\\\\]')
    rxStripExt = re.compile('\\.[^.]*$')
    rxBadSentence = re.compile('[^а-яё./ -]')
    rxWord = re.compile('\\b\\w[\\w-]*\\b')

    def __init__(self, main_tiers, aligned_tiers, tier_languages, sound_path, stats_path):
        self.srcExt = 'eaf'
        self.tlis = {}  # time labels
        self.participants = {}  # main tier ID -> participant ID
        self.segmentTree = {}  # aID -> (contents, parent aID, tli1, tli2)
        self.segmentChildren = {}  # (aID, child tier type) -> [child aID]
        self.corpusSettings = {'main_tiers': ["transcription"],
                               'aligned_tiers': [],
                               'tier_languages': {"transcription": "russian"},
                               'sound_path': sound_path,
                               'stats_path': stats_path}
        self.phraseID = 0

    def convert_sentence(self, text):
        text = text.strip().lower()
        text = re.sub('\\[нрзб|говорит [^\\[\\]]+\\] *', '', text)
        text = re.sub('[/\\[\\]"?!]+', '', text)
        text = text.replace('...', '')
        return text

    def is_bad_sentence(self, text):
        # This function is not used at present
        if self.rxBadSentence.search(text) is not None:
            return True
        return False

    def str_duration(self, duration):
        """
        Present duration in a human-readable form.
        """
        totalDurHours = round(duration // 3600)
        totalDurMinutes = round((duration - totalDurHours * 3600) // 60)
        totalDurSeconds = round(duration % 60)
        return str(totalDurHours).zfill(2) + ':' + str(totalDurMinutes).zfill(2) + ':' + str(totalDurSeconds).zfill(2)

    def get_tlis(self, srcTree):
        """
        Retrieve and return all time labels from the XML tree.
        """
        tlis = {}
        iTli = 0
        for tli in srcTree.xpath('/ANNOTATION_DOCUMENT/TIME_ORDER/TIME_SLOT'):
            timeValue = ''
            if 'TIME_VALUE' in tli.attrib:
                timeValue = tli.attrib['TIME_VALUE']
            tlis[tli.attrib['TIME_SLOT_ID']] = {'n': iTli, 'time': timeValue}
            iTli += 1
        return tlis

    def traverse_tree(self, srcTree, callback):
        """
        Iterate over all tiers in the XML tree and call the callback function
        for each of them.
        """
        for tierNode in srcTree.xpath('/ANNOTATION_DOCUMENT/TIER'):
            if 'TIER_ID' not in tierNode.attrib:
                continue
            callback(tierNode)

    def cb_build_segment_tree(self, tierNode):
        tierType = ''  # analysis tiers: word/POS/gramm/gloss etc.
        if 'analysis_tiers' in self.corpusSettings:
            for k, v in self.corpusSettings['analysis_tiers'].items():
                if not k.startswith('^'):
                    k = '^' + k
                if not k.endswith('$'):
                    k += '$'
                try:
                    rxTierID = re.compile(k)
                    if (rxTierID.search(tierNode.attrib['TIER_ID']) is not None
                            or rxTierID.search(tierNode.attrib['LINGUISTIC_TYPE_REF']) is not None):
                        tierType = v
                        break
                except:
                    print('Except')
        for segNode in tierNode.xpath('ANNOTATION/REF_ANNOTATION | ANNOTATION/ALIGNABLE_ANNOTATION'):
            if 'ANNOTATION_ID' not in segNode.attrib:
                continue
            aID = segNode.attrib['ANNOTATION_ID']
            try:
                segContents = segNode.xpath('ANNOTATION_VALUE')[0].text.strip()
            except AttributeError:
                segContents = ''
            try:
                segParent = segNode.attrib['ANNOTATION_REF']
            except KeyError:
                segParent = None
            tli1, tli2 = None, None
            if 'TIME_SLOT_REF1' in segNode.attrib:
                tli1 = segNode.attrib['TIME_SLOT_REF1']
            elif segParent in self.segmentTree and self.segmentTree[segParent][2] is not None:
                tli1 = self.segmentTree[segParent][2]
            if 'TIME_SLOT_REF2' in segNode.attrib:
                tli2 = segNode.attrib['TIME_SLOT_REF2']
            elif segParent in self.segmentTree and self.segmentTree[segParent][3] is not None:
                tli2 = self.segmentTree[segParent][3]
            self.segmentTree[aID] = (segContents, segParent, tli1, tli2)
            if segParent is None:
                continue
            if len(tierType) > 0:
                try:
                    self.segmentChildren[(segParent, tierType)].append(aID)
                except KeyError:
                    self.segmentChildren[(segParent, tierType)] = [aID]

    def build_segment_tree(self, srcTree):
        """
        Read the entire XML tree and save all segment data (contents, links to
        the parents and timestamps, if any).
        """
        self.segmentTree = {}
        self.segmentChildren = {}
        self.traverse_tree(srcTree, self.cb_build_segment_tree)

    def add_src_alignment(self, sent, tli1, tli2, srcFile):
        """
        Add the alignment of the sentence with the sound/video. If
        word-level time data is available, align words, otherwise
        align the whole sentence.
        """
        sentAlignments = []
        ts1 = self.tlis[tli1]['time']
        ts2 = self.tlis[tli2]['time']
        sentAlignments.append({'off_start_src': float(ts1) / EAF_TIME_MULTIPLIER,
                               'off_end_src': float(ts2) / EAF_TIME_MULTIPLIER,
                               'src': srcFile})
        sent['src_alignment'] = sentAlignments

    def process_tier(self, tierNode, aID2pID, srcFile, alignedTier=False):
        """
        Extract segments from the tier node and iterate over them, returning
        them as JSON sentences. If alignedTier is False, store the start and end
        timestamps in the dictionary aID2pID.
        If alignedTier is True, use the information from aID2pID for establishing
        time boundaries of the sentences.
        """
        lang = ''
        # We have to find out what language the tier represents.
        # First, check the tier type. If it is not associated with any language,
        # check all tier ID regexes.
        if 'TIER_ID' not in tierNode.attrib:
            return
        if ('LINGUISTIC_TYPE_REF' in tierNode.attrib and
                tierNode.attrib['LINGUISTIC_TYPE_REF'] in self.corpusSettings['tier_languages']):
            lang = self.corpusSettings['tier_languages'][tierNode.attrib['LINGUISTIC_TYPE_REF']]
        else:
            for k, v in self.corpusSettings['tier_languages'].items():
                if not k.startswith('^'):
                    k = '^' + k
                if not k.endswith('$'):
                    k += '$'
                try:
                    rxTierID = re.compile(k)
                    if rxTierID.search(tierNode.attrib['TIER_ID']) is not None:
                        lang = v
                        break
                except:
                    continue
        if len(lang) <= 0:
            return

        speaker = ''
        if not alignedTier and 'PARTICIPANT' in tierNode.attrib:
            speaker = tierNode.attrib['PARTICIPANT']
            self.participants[tierNode.attrib['TIER_ID']] = speaker
        else:
            if ('PARENT_REF' in tierNode.attrib
                    and tierNode.attrib['PARENT_REF'] in self.participants):
                speaker = self.participants[tierNode.attrib['PARENT_REF']]
            elif 'PARTICIPANT' in tierNode.attrib:
                speaker = tierNode.attrib['PARTICIPANT']

        segments = tierNode.xpath('ANNOTATION/REF_ANNOTATION | ANNOTATION/ALIGNABLE_ANNOTATION')

        for segNode in segments:
            if ('ANNOTATION_ID' not in segNode.attrib
                    or segNode.attrib['ANNOTATION_ID'] not in self.segmentTree):
                continue
            segData = self.segmentTree[segNode.attrib['ANNOTATION_ID']]
            if not alignedTier:
                if segData[2] is None or segData[3] is None:
                    continue
                tli1 = segData[2]
                tli2 = segData[3]
            elif segData[1] is not None:
                aID = segData[1]
                pID, tli1, tli2 = aID2pID[aID]
            else:
                continue
            text = segData[0]
            curSent = {'text': text, 'words': None, 'lang': lang,
                       'meta': {'speaker': speaker}}
            if len(self.corpusSettings['aligned_tiers']) > 0:
                if not alignedTier:
                    self.pID += 1
                    aID = segNode.attrib['ANNOTATION_ID']
                    aID2pID[aID] = (self.pID, tli1, tli2)
                    paraAlignment = {'off_start': 0, 'off_end': len(curSent['text']), 'para_id': self.pID}
                    curSent['para_alignment'] = [paraAlignment]
                else:
                    paraAlignment = {'off_start': 0, 'off_end': len(curSent['text']), 'para_id': pID}
                    curSent['para_alignment'] = [paraAlignment]
            self.add_src_alignment(curSent, tli1, tli2, srcFile)
            yield curSent

    def get_sentences(self, srcTree, srcFile):
        """
        Iterate over sentences in the XML tree.
        """
        # mainTierTypes = '(' + ' | '.join('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + x + '\'] | ' +
        #                                  '/ANNOTATION_DOCUMENT/TIER[@TIER_ID=\'' + x + '\']'
        #                                  for x in self.corpusSettings['main_tiers']) + ')'
        # mainTiers = srcTree.xpath(mainTierTypes)
        mainTiers = []
        alignedTiers = []
        for tierNode in srcTree.xpath('/ANNOTATION_DOCUMENT/TIER'):
            for tierRegex in self.corpusSettings['main_tiers']:
                if not tierRegex.startswith('^'):
                    tierRegex = '^' + tierRegex
                if not tierRegex.endswith('$'):
                    tierRegex += '$'
                try:
                    if re.search(tierRegex, tierNode.attrib['TIER_ID']) is not None:
                        mainTiers.append(tierNode)
                        break
                    elif ('LINGUISTIC_TYPE_REF' in tierNode.attrib
                          and re.search(tierRegex, tierNode.attrib['LINGUISTIC_TYPE_REF']) is not None):
                        mainTiers.append(tierNode)
                        break
                except:
                    pass
            for tierRegex in self.corpusSettings['aligned_tiers']:
                if not tierRegex.startswith('^'):
                    tierRegex = '^' + tierRegex
                if not tierRegex.endswith('$'):
                    tierRegex += '$'
                try:
                    if re.search(tierRegex, tierNode.attrib['TIER_ID']) is not None:
                        alignedTiers.append(tierNode)
                        break
                    elif ('LINGUISTIC_TYPE_REF' in tierNode.attrib
                          and re.search(tierRegex, tierNode.attrib['LINGUISTIC_TYPE_REF']) is not None):
                        alignedTiers.append(tierNode)
                        break
                except:
                    pass
        if len(mainTiers) <= 0:
            return
        # if len(self.corpusSettings['aligned_tiers']) > 0:
        #     alignedTierTypes = '(' + ' | '.join('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + x + '\'] | ' +
        #                                         '/ANNOTATION_DOCUMENT/TIER[@TIER_ID=\'' + x + '\']'
        #                                         for x in self.corpusSettings['aligned_tiers']) + ')'
        #     alignedTiers = srcTree.xpath(alignedTierTypes)
        aID2pID = {}  # annotation ID -> (pID, tli1, tli2) correspondence
        for tier in mainTiers:
            for sent in self.process_tier(tier, aID2pID, srcFile, alignedTier=False):
                yield sent
        for tier in alignedTiers:
            for sent in self.process_tier(tier, aID2pID, srcFile, alignedTier=True):
                yield sent

    def process_file(self, textSrc, dictFreqBySpeaker, dictDurBySpeaker):
        srcTree = etree.XML(textSrc)
        self.tlis = self.get_tlis(srcTree)
        self.build_segment_tree(srcTree)

        sentences = [s for s in self.get_sentences(srcTree, '')]
        if len(sentences) <= 0:
            return 0, 0

        tokenCount = 0
        sentences.sort(key=lambda s: (s['lang'], s['src_alignment'][0]['off_start_src']))
        for i in range(len(sentences) - 1):
            sentences[i]['text'] = self.convert_sentence(sentences[i]['text'])
            if len(sentences[i]['text']) <= 1:
                continue
            speaker = sentences[i]['meta']['speaker']
            if speaker not in dictFreqBySpeaker:
                dictFreqBySpeaker[speaker] = {}
            for token in EafStats.rxWord.findall(sentences[i]['text']):
                tokenCount += 1
                try:
                    dictFreqBySpeaker[speaker][token] += 1
                except KeyError:
                    dictFreqBySpeaker[speaker][token] = 1
            if speaker not in dictDurBySpeaker:
                dictDurBySpeaker[speaker] = 0
            dictDurBySpeaker[speaker] += sentences[i]['src_alignment'][0]['off_end_src'] \
                                         - sentences[i]['src_alignment'][0]['off_start_src']
        duration = sentences[-1]['src_alignment'][0]['off_end_src'] - sentences[0]['src_alignment'][0]['off_start_src']
        # print(fnameSrc, duration)
        return duration, tokenCount

    def sound_duration(self, dirName):
        """
        Calculate total duration of sound files in a folder
        """
        duration = 0
        for root, dirs, files in os.walk(dirName):
            for fname in files:
                if re.sub('.*\\.', '.', fname.lower()) not in EafStats.mediaExtensions:
                    continue
                fname = os.path.join(root, fname)
                try:
                    with contextlib.closing(wave.open(fname, 'r')) as f:
                        frames = f.getnframes()
                        rate = f.getframerate()
                        duration += frames / float(rate)
                except:
                    # This is slower, but works for more formats
                    (source_rate, source_sig) = wav.read(fname)
                    duration += len(source_sig) / float(source_rate)
        return duration

    def print_stats(self, dirnameOut, dictFreqBySpeaker, dictDurBySpeaker):
        fDur = open(os.path.join(dirnameOut, 'duration_by_speaker.json'), 'w', encoding='utf-8')
        json.dump(dictDurBySpeaker, fDur, ensure_ascii=False, indent=2, sort_keys=True)
        fDur.close()
        fFreq = open(os.path.join(dirnameOut, 'tokens_by_speaker.json'), 'w', encoding='utf-8')
        json.dump(dictFreqBySpeaker, fFreq, ensure_ascii=False, indent=2, sort_keys=True)
        fFreq.close()

    def log(self, logDir, message):
        now = datetime.datetime.now()
        fOut = open(os.path.join(logDir, 'log.txt'), 'a', encoding='utf-8')
        fOut.write(now.strftime("%Y-%m-%d %H:%M:%S") + '\t' + message + '\n')
        fOut.close()

    def process_repo(self, repo):
        duration = 0
        transcrDuration = 0
        tokenCount = 0
        dictFreqBySpeaker = {}
        dictDurBySpeaker = {}
        dirnameOut = self.corpusSettings['stats_path']

        if not os.path.exists(dirnameOut):
            os.makedirs(dirnameOut)
        fOut = open(os.path.join(dirnameOut, 'log.txt'), 'w', encoding='utf-8')
        fOut.close()

        # Calculate token counts and transcribed duration based on ELAN files
        tree = repo.head.commit.tree
        for item in tree.traverse():
            if item.type == 'tree':
                continue
            fname = item.path
            fileExt = os.path.splitext(fname.lower())[1][1:]
            if fileExt != self.srcExt:
                continue
            text = item.data_stream.read()
            self.log(dirnameOut, fname + ' read.')
            curDuration, curTokenCount = self.process_file(text, dictFreqBySpeaker, dictDurBySpeaker)
            self.log(dirnameOut, fname + ': ' + str(curDuration) + 's., ' + str(curTokenCount) + ' words.')
            transcrDuration += curDuration
            tokenCount += curTokenCount

        self.log(dirnameOut, 'Total transcribed duration: ' + self.str_duration(transcrDuration) + '.')
        self.log(dirnameOut, 'Total tokens: ' + str(tokenCount) + '.')
        # print('Total transcribed duration: ' + self.str_duration(transcrDuration) + '.')
        print('Total tokens: ' + str(tokenCount) + '.')

        # Calculate total sound duration based on sound files, which reside
        # in a separate place
        if os.path.exists(self.corpusSettings['sound_path']):
            print('Calculating sound duration...')
            duration = self.sound_duration(self.corpusSettings['sound_path'])
            print('Total sound duration: ' + self.str_duration(duration) + '.')
            self.log(dirnameOut, 'Total sound duration: ' + self.str_duration(duration) + '.')
        dictDurBySpeaker['#TOTAL_SOUND_DURATION'] = duration
        self.print_stats(dirnameOut, dictFreqBySpeaker, dictDurBySpeaker)


if __name__ == '__main__':
    pass
