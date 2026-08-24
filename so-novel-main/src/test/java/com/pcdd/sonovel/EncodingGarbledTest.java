package com.pcdd.sonovel;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.*;
import java.util.List;

class EncodingGarbledTest {

    private static final List<Charset> SOURCE_CHARSETS = List.of(
            // UTF-8: Windows Terminal、PowerShell 7、Linux/macOS 用户、启用 UTF-8 Beta 区域
            StandardCharsets.UTF_8,
            // 简体中文 Windows: CP936，Java 映射为 GBK
            Charset.forName("GBK"),
            // 繁体中文 Windows 台湾: CP950
            Charset.forName("Big5"),
            // 繁体中文 Windows 香港: Big5 扩展字符
            Charset.forName("Big5-HKSCS")
    );


    private static final List<Charset> TARGET_CHARSETS = List.of(
            StandardCharsets.UTF_8,
            Charset.forName("GBK"),
            Charset.forName("Big5"),
            Charset.forName("Big5-HKSCS")
    );

    @ParameterizedTest
    @ValueSource(strings = {
            "hello 中文测试",
    })
    void testEncodingGarbled(String text) {

        System.out.printf("===== 《%s》乱码全场景穷举模拟 =====%n%n", text);

        for (Charset source : SOURCE_CHARSETS) {

            System.out.printf("【原始数据 %s】%n", source.displayName());

            byte[] bytes = text.getBytes(source);

            for (Charset target : TARGET_CHARSETS) {

                if (source.equals(target)) {
                    continue;
                }

                String result = decode(bytes, target);

                System.out.printf("  -> 使用 %-15s 解码: %s%n", target.displayName(), result);
            }

            System.out.println();
        }
    }


    /**
     * 模拟 Python errors='replace'
     */
    private static String decode(byte[] bytes, Charset charset) {

        CharsetDecoder decoder = charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPLACE)
                .onUnmappableCharacter(CodingErrorAction.REPLACE);

        try {
            CharBuffer buffer = decoder.decode(ByteBuffer.wrap(bytes));

            return buffer.toString();

        } catch (CharacterCodingException e) {
            return "[解码失败]";
        }
    }
}