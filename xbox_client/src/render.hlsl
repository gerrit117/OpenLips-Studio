struct VertexInput { float2 position : POSITION; float2 uv : TEXCOORD0; float4 color : COLOR0; };
struct VertexOutput { float4 position : POSITION; float2 uv : TEXCOORD0; float4 color : COLOR0; };
VertexOutput vertex(VertexInput input) {
    VertexOutput output;
    output.position = float4(input.position.x / 640.0 - 1.0, 1.0 - input.position.y / 360.0, 0, 1);
    output.uv = input.uv; output.color = input.color;
    return output;
}
sampler2D image : register(s0);
float4 pixel(VertexOutput input) : COLOR0 { return tex2D(image,input.uv)*input.color; }
