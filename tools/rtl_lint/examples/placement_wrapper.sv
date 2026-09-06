module demo_core #(parameter W = 8) (
  input wire [W-1:0] d,
  output wire [W-1:0] q
);
  assign q = ~d;
endmodule

module placement_wrapper_sv # (parameter W=8) (
  input logic clk,
  input logic [W-1:0] din,
  output wire [W-1:0] dout
);
  (* SHREG_EXTRACT = "no" *) logic [W-1:0] in_1, in_2, out_1, out_2;
  wire [W-1:0] core_q;
  always_ff @(posedge clk) begin
    in_1 <= din;
    in_2 <= in_1;
    out_1 <= core_q;
    out_2 <= out_1;
  end
  demo_core #(.W(W)) core_i (.d(in_2), .q(core_q));
  assign dout = out_2;
endmodule
